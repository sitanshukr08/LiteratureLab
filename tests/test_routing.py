import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from literaturelab.providers import Gemini, Groq, ProviderError, ProviderRouter
from literaturelab.synthesis import Draft


@pytest.fixture(autouse=True)
def isolated_provider_environment(monkeypatch, tmp_path):
    for name in ('GEMINI_API_KEY', 'GROQ_API_KEY', 'LLM_PROVIDER', 'GEMINI_MODEL', 'GROQ_MODEL'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr('literaturelab.providers.tempfile.tempdir', str(tmp_path))
    monkeypatch.setattr('literaturelab.providers.time.sleep', lambda _: None)


def response(body, status=200):
    return SimpleNamespace(returncode=0, stdout=json.dumps(body) + '\n' + str(status))


def success():
    answer = {'claims': [], 'insufficient_evidence': True, 'limitations': ['No evidence.']}
    return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(answer)}]}}],
            'usageMetadata': {'promptTokenCount': 20, 'candidatesTokenCount': 10, 'totalTokenCount': 30}}


def test_gemini_structured_transport_keeps_auth_key_out_of_argv_and_body(monkeypatch):
    engine = Gemini(); engine.key = 'AQ.test-token-1234567890'
    calls = []
    def transport(args, **kwargs):
        calls.append(args)
        assert not any(engine.key in str(arg) for arg in args)
        assert engine.key in kwargs['input'] and 'x-goog-api-key:' in kwargs['input']
        assert '?key=' not in kwargs['input']
        payload = json.loads(Path(args[args.index('--data-binary') + 1][1:]).read_text())
        assert engine.key not in json.dumps(payload)
        assert payload['systemInstruction']['parts'][0]['text'] == 'Use supplied sources.'
        assert payload['contents'][0]['role'] == 'user'
        assert payload['generationConfig']['responseMimeType'] == 'application/json'
        assert 'responseJsonSchema' in payload['generationConfig']
        assert 'tools' not in payload
        return response(success())
    monkeypatch.setattr('literaturelab.providers.subprocess.run', transport)
    answer, usage = engine.complete([{'role': 'system', 'content': 'Use supplied sources.'},
                                     {'role': 'user', 'content': 'explain it'}], Draft)
    assert answer['insufficient_evidence'] and usage['total_tokens'] == 30 and len(calls) == 1


@pytest.mark.parametrize('status,expected,allowed', [(401, 503, True), (403, 503, True),
                                                  (404, 502, True), (429, 429, True),
                                                  (503, 502, True), (400, 502, False)])
def test_gemini_safe_errors_and_fallback_policy(monkeypatch, status, expected, allowed):
    engine = Gemini(); engine.key = 'AQ.test-token-1234567890'
    calls = []
    def transport(*args, **kwargs):
        calls.append(1)
        return response({'error': {'message': engine.key + ' private detail'}}, status)
    monkeypatch.setattr('literaturelab.providers.subprocess.run', transport)
    with pytest.raises(ProviderError) as exc:
        engine.complete([], Draft)
    assert exc.value.status == expected and exc.value.fallback_allowed is allowed
    assert engine.key not in str(exc.value) and 'private detail' not in str(exc.value)
    assert len(calls) <= 2


@pytest.mark.parametrize('body', [
    {'promptFeedback': {'blockReason': 'SAFETY'}},
    {'candidates': [{'finishReason': 'SAFETY'}]},
    {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': '{}'}]}}]},
    {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"claims":"bad"}'}]}}]},
])
def test_blocked_truncated_or_invalid_gemini_answers_never_trigger_fallback(monkeypatch, body):
    engine = Gemini(); engine.key = 'AQ.test-token-1234567890'
    monkeypatch.setattr('literaturelab.providers.subprocess.run', lambda *a, **k: response(body))
    with pytest.raises(ProviderError) as exc:
        engine.complete([], Draft)
    assert not exc.value.fallback_allowed


@pytest.mark.parametrize('body', [[], None, {'candidates': [None]},
                                {'candidates': [{'finishReason': 'STOP', 'content': {'parts': []}}]}])
def test_malformed_gemini_envelopes_raise_safe_provider_error(monkeypatch, body):
    engine = Gemini(); engine.key = 'AQ.test-token-1234567890'
    monkeypatch.setattr('literaturelab.providers.subprocess.run', lambda *a, **k: response(body))
    with pytest.raises(ProviderError) as exc: engine.complete([], Draft)
    assert not exc.value.fallback_allowed


def test_invalid_key_and_model_cannot_inject_curl_configuration(monkeypatch):
    engine = Gemini(); engine.key = 'AQ.valid\nheader="unsafe"'
    monkeypatch.setattr('literaturelab.providers.subprocess.run', lambda *a, **k: pytest.fail('Must reject before transport'))
    with pytest.raises(ProviderError): engine.complete([], Draft)
    engine.key = 'AQ.test-token-1234567890'; engine.model = 'model\nheader="unsafe"'
    with pytest.raises(ProviderError): engine.complete([], Draft)


def test_router_auto_orders_configured_providers_and_manual_modes_are_strict(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'AQ.test-token-1234567890')
    monkeypatch.setenv('GROQ_API_KEY', 'gsk_testsecret')
    router = ProviderRouter()
    assert [p.name for p in router.candidates('auto')] == ['gemini', 'groq']
    assert [p.name for p in router.candidates('groq')] == ['groq']
    assert [p.name for p in router.candidates('gemini')] == ['gemini']
    assert router.cache_identity('auto') != router.cache_identity('groq')
    public = json.dumps(router.providers_status()) + json.dumps(router.cache_identity('auto'))
    assert 'gsk_testsecret' not in public and 'AQ.test-token-1234567890' not in public


def test_router_missing_or_placeholder_keys_not_advertised_as_ready(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'replace_with_your_free_tier_key')
    monkeypatch.setenv('GROQ_API_KEY', 'gsk_testsecret')
    router = ProviderRouter()
    assert [p.name for p in router.candidates('auto')] == ['groq']
    with pytest.raises(ProviderError): router.candidates('gemini')
    monkeypatch.delenv('GROQ_API_KEY')
    with pytest.raises(ProviderError): ProviderRouter().candidates('auto')


def test_groq_fallback_classification_distinguishes_quota_from_invalid_schema(monkeypatch):
    engine = Groq(); engine.key = 'gsk_testsecret'
    monkeypatch.setattr('literaturelab.providers.subprocess.run', lambda *a, **k: response({}, 429))
    with pytest.raises(ProviderError) as quota: engine.complete([], Draft)
    assert quota.value.fallback_allowed
    monkeypatch.setattr('literaturelab.providers.subprocess.run', lambda *a, **k: response({'choices': []}))
    with pytest.raises(ProviderError) as invalid: engine.complete([], Draft)
    assert not invalid.value.fallback_allowed


def test_groq_error_diagnostics_cannot_retain_a_key_shaped_code(monkeypatch):
    engine = Groq(); engine.key = 'gsk_testsecret'
    monkeypatch.setattr('literaturelab.providers.subprocess.run',
                        lambda *a, **k: response({'error': {'code': engine.key}}, 401))
    with pytest.raises(ProviderError):
        engine.complete([], Draft)
    assert engine.key not in json.dumps(engine.last_failure)
