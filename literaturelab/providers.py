"""Hosted model adapters; generation and review stay with one selected provider."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from dotenv import load_dotenv
from pydantic import ValidationError

load_dotenv(Path(__file__).resolve().parents[1] / '.env')


class ProviderError(RuntimeError):
    def __init__(self, message, status=502, *, fallback_allowed=False):
        super().__init__(message)
        self.status = status
        self.fallback_allowed = fallback_allowed


class Groq:
    name = "groq"
    """curl transport uses Windows networking; secrets go through stdin, never argv."""
    def __init__(self):
        self.model = os.getenv('GROQ_MODEL', 'openai/gpt-oss-120b')
        self.key = os.getenv('GROQ_API_KEY', '')
        self.remaining_tokens = None
        self.token_limit = None
        self.quota_observed = 0
        self.last_http_status = None
        self.last_failure = None

    def pace(self, needed):
        if self.remaining_tokens is None or not self.token_limit:
            return
        estimated_available = min(self.token_limit, self.remaining_tokens +
                                  (time.monotonic() - self.quota_observed) * self.token_limit / 60)
        delay = (needed - estimated_available) * 60 / self.token_limit
        if delay > 0:
            time.sleep(min(45, delay + 1))

    def observe_quota(self, headers):
        values = dict((key.lower(), value.strip()) for key, value in re.findall(r'(?im)^([\w-]+):\s*([^\r\n]+)', headers))
        for header, attr in [('x-ratelimit-remaining-tokens','remaining_tokens'),('x-ratelimit-limit-tokens','token_limit')]:
            if values.get(header, '').isdigit():
                setattr(self, attr, int(values[header]))
        self.quota_observed = time.monotonic()

    def complete(self, messages, schema):
        self.last_failure = None
        if not re.fullmatch(r'gsk_[A-Za-z0-9_-]+', self.key):
            raise ProviderError('Configure GROQ_API_KEY in the local .env, then restart.', 503, fallback_allowed=True)
        payload = {'model': self.model, 'messages': messages, 'temperature': 0.1,
                   'max_completion_tokens': 1500, 'reasoning_effort': 'low',
                   'response_format': {'type':'json_schema', 'json_schema':{
                       'name':schema.__name__, 'strict':True, 'schema':schema.model_json_schema()}}}
        self.pace(int(sum(len(m['content']) for m in messages) / 3.5) + payload['max_completion_tokens'])
        # No hosted tools are requested; account billing is controlled by the provider account.
        with tempfile.TemporaryDirectory(prefix='literaturelab-') as directory:
            body_path = Path(directory) / 'request.json'
            header_path = Path(directory) / 'headers.txt'
            body_path.write_text(json.dumps(payload), encoding='utf-8')
            config = ('url = "https://api.groq.com/openai/v1/chat/completions"\n'
                      'header = "Content-Type: application/json"\n'
                      f'header = "Authorization: Bearer {self.key}"\n')
            schema_failures = 0
            for attempt in range(3):
                try:
                    proc = subprocess.run(['curl.exe' if os.name == 'nt' else 'curl', '--config', '-', '--silent', '--show-error',
                                           '--max-time', '90', '--dump-header', str(header_path),
                                           '--data-binary', '@' + str(body_path), '--write-out', '\n%{http_code}'],
                                          input=config, text=True, encoding='utf-8', capture_output=True, timeout=100,
                                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise ProviderError('Groq connection timed out. Check internet access and retry.', 503, fallback_allowed=True) from exc
                body, _, status_text = proc.stdout.rpartition('\n')
                status = int(status_text) if status_text.isdigit() else 0
                self.last_http_status = status
                if proc.returncode or status == 0:
                    raise ProviderError('Cannot reach Groq. Check internet access and retry.', 503, fallback_allowed=True)
                headers = header_path.read_text(errors='replace') if header_path.exists() else ''
                self.observe_quota(headers)
                if status != 200:
                    try:
                        parsed_error = json.loads(body)
                        error = parsed_error.get('error', {}) if isinstance(parsed_error, dict) else {}
                        error = error if isinstance(error, dict) else {}
                        code = str(error.get('code', ''))
                        self.last_failure = {'http_status':status, 'code':code if code in {'json_validate_failed','rate_limit_exceeded','invalid_api_key','model_not_found','insufficient_quota'} else 'provider-error'}
                    except ValueError:
                        self.last_failure = {'http_status':status,'code':'unreadable-response'}
                if status == 400 and self.last_failure.get('code') == 'json_validate_failed' and attempt < 2:
                    # Provider decoding failed before a usable answer existed; no content is scored or selected.
                    schema_failures += 1
                    time.sleep(1)
                    continue
                if status in {429, 500, 502, 503} and attempt < 2:
                    retry = re.search(r'(?im)^retry-after:\s*(\d+)', headers)
                    delay = int(retry.group(1)) if retry else 6 * (attempt + 1)
                    if delay > 45:
                        break
                    time.sleep(max(1, delay))
                    continue
                if status != 200:
                    break
                try:
                    result = json.loads(body)
                    choice = result['choices'][0]
                    if choice['finish_reason'] != 'stop':
                        raise ProviderError('Groq response reached its output limit. Try a narrower question.')
                    answer = schema.model_validate_json(choice['message']['content']).model_dump()
                    usage = dict(result.get('usage', {}), transport_attempts=attempt + 1, schema_failures_retried=schema_failures)
                    return answer, usage
                except (AttributeError, KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
                    raise ProviderError('Groq returned an invalid structured answer. No unverified answer was saved.') from exc
            if status in {401, 403}:
                raise ProviderError('Groq rejected the API key or model access. Update .env and restart.', 503, fallback_allowed=True)
            if status == 429:
                raise ProviderError('Groq free-tier quota reached. Wait for the limit to reset and retry.', 429, fallback_allowed=True)
            raise ProviderError('Groq could not complete this request. Retry later.', 502, fallback_allowed=status in {500, 502, 503, 504})


class Gemini:
    name = 'gemini'

    def __init__(self):
        # Current model and free-tier availability: https://ai.google.dev/gemini-api/docs/pricing
        self.model = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
        self.key = os.getenv('GEMINI_API_KEY', '')
        self.last_http_status = None
        self.last_failure = None

    def complete(self, messages, schema):
        # Auth keys include AQ. tokens; do not assume the older AIza prefix.
        # https://ai.google.dev/gemini-api/docs/api-key
        if not valid_key(self.key):
            raise ProviderError('Configure GEMINI_API_KEY in the local .env, then restart.', 503, fallback_allowed=True)
        if not re.fullmatch(r'gemini-[A-Za-z0-9._-]{1,100}', self.model):
            raise ProviderError('Check GEMINI_MODEL in the local .env, then restart.', 503)
        # REST fields: https://ai.google.dev/api/generate-content#v1beta.GenerationConfig
        payload = {'contents': [{'role': 'model' if m['role'] == 'assistant' else 'user',
                                 'parts': [{'text': m['content']}]} for m in messages if m['role'] != 'system'],
                   'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 4096,
                                        'responseMimeType': 'application/json',
                                        'responseJsonSchema': schema.model_json_schema()}}
        if self.model.startswith('gemini-3'):
            payload['generationConfig']['thinkingConfig'] = {'thinkingLevel': 'LOW'}
        system = '\n'.join(m['content'] for m in messages if m['role'] == 'system')
        if system:
            payload['systemInstruction'] = {'parts': [{'text': system}]}
        if not payload['contents']:
            payload['contents'] = [{'role': 'user', 'parts': [{'text': 'Return the requested structured response.'}]}]
        self.last_failure = None
        with tempfile.TemporaryDirectory(prefix='literaturelab-') as directory:
            body_path, header_path = Path(directory) / 'request.json', Path(directory) / 'headers.txt'
            body_path.write_text(json.dumps(payload), encoding='utf-8')
            config = (f'url = "https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"\n'
                      'header = "Content-Type: application/json"\n'
                      f'header = "x-goog-api-key: {self.key}"\n')
            for attempt in range(2):
                try:
                    proc = subprocess.run(['curl.exe' if os.name == 'nt' else 'curl', '--config', '-', '--silent', '--show-error',
                                           '--max-time', '90', '--dump-header', str(header_path),
                                           '--data-binary', '@' + str(body_path), '--write-out', '\n%{http_code}'],
                                          input=config, text=True, encoding='utf-8', capture_output=True, timeout=100,
                                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise ProviderError('Gemini connection timed out. Check internet access and retry.', 503, fallback_allowed=True) from exc
                body, _, status_text = proc.stdout.rpartition('\n')
                status = int(status_text) if status_text.isdigit() else 0
                self.last_http_status = status
                if proc.returncode or status == 0:
                    raise ProviderError('Cannot reach Gemini. Check internet access and retry.', 503, fallback_allowed=True)
                if status != 200:
                    # Provider response text can contain credentials or source text. Never relay it.
                    self.last_failure = {'http_status': status, 'code': 'provider-error'}
                    if status in {429, 500, 502, 503, 504} and attempt == 0:
                        headers = header_path.read_text(errors='replace') if header_path.exists() else ''
                        retry = re.search(r'(?im)^retry-after:\s*(\d+)', headers)
                        delay = int(retry.group(1)) if retry else 1
                        if delay <= 5:
                            time.sleep(max(1, delay))
                            continue
                    if status in {401, 403}:
                        raise ProviderError('Gemini rejected the API key or model access. Update .env and restart.', 503, fallback_allowed=True)
                    if status == 429:
                        raise ProviderError('Gemini free-tier quota reached. Wait for the limit to reset and retry.', 429, fallback_allowed=True)
                    raise ProviderError('Gemini could not complete this request. Check model configuration and retry later.', 502,
                                        fallback_allowed=status in {404, 500, 502, 503, 504})
                try:
                    result = json.loads(body)
                    if result.get('promptFeedback', {}).get('blockReason'):
                        raise ProviderError('Gemini declined this request. No answer was saved.', 422)
                    choice = result['candidates'][0]
                    if choice.get('finishReason') != 'STOP':
                        raise ProviderError('Gemini stopped before a complete answer. Try a narrower question; no answer was saved.', 422)
                    # Thinking parts are not user-facing structured output.
                    content = ''.join(p['text'] for p in choice['content']['parts'] if 'text' in p and not p.get('thought'))
                    answer = schema.model_validate_json(content).model_dump()
                    usage = result.get('usageMetadata', {})
                    return answer, {'prompt_tokens': usage.get('promptTokenCount', 0),
                                    'completion_tokens': usage.get('candidatesTokenCount', 0),
                                    'total_tokens': usage.get('totalTokenCount', 0),
                                    'transport_attempts': attempt + 1, 'schema_failures_retried': 0}
                except (AttributeError, KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
                    raise ProviderError('Gemini returned an invalid structured answer. No unverified answer was saved.') from exc


def valid_key(value):
    return bool(re.fullmatch(r'[A-Za-z0-9._-]{10,512}', value)) and not value.startswith(('replace_', 'your_'))


class ProviderRouter:
    """Select providers only; the caller retries the complete generation/review workflow."""
    def __init__(self):
        self.preference = os.getenv('LLM_PROVIDER', 'auto').lower()
        self.providers = {'gemini': Gemini(), 'groq': Groq()}

    def _order(self, preference=None):
        preference = preference or self.preference
        if preference not in {'auto', 'groq', 'gemini'}:
            raise ProviderError('Choose auto, groq or gemini as the generation provider.', 503)
        return ['gemini', 'groq'] if preference == 'auto' else [preference]

    def candidates(self, preference=None):
        configured = [self.providers[name] for name in self._order(preference) if valid_key(self.providers[name].key)]
        if not configured:
            raise ProviderError('No configured generation provider is available. Add a key in .env and restart.', 503)
        return configured

    def providers_status(self):
        return [{'name': p.name, 'model': p.model, 'key_configured': valid_key(p.key)} for p in self.providers.values()]

    def cache_identity(self, preference=None):
        return {'mode': preference or self.preference,
                'providers': [(name, self.providers[name].model) for name in self._order(preference) if valid_key(self.providers[name].key)]}

    def _primary(self):
        order = self._order()
        return next((self.providers[name] for name in order if valid_key(self.providers[name].key)), self.providers[order[0]])

    @property
    def model(self): return self._primary().model

    @property
    def name(self): return self._primary().name

    @property
    def key(self): return self._primary().key

    def complete(self, messages, schema):
        # Convenience for a single call; it deliberately performs no provider fallback.
        return self.candidates()[0].complete(messages, schema)

