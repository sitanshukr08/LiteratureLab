import json
from types import SimpleNamespace
import pytest
from literaturelab.providers import Groq, ProviderError
from literaturelab.synthesis import Draft


@pytest.fixture(autouse=True)
def local_temp_directory(monkeypatch, tmp_path):
    # Keep test-created request files in pytest's isolated, writable test directory.
    monkeypatch.setattr('literaturelab.providers.tempfile.tempdir', str(tmp_path))


@pytest.mark.parametrize('status,expected', [('401',503),('429',429),('500',502)])
def test_provider_errors_are_safe_and_bounded(monkeypatch, status, expected):
    engine = Groq(); engine.key = 'gsk_testsecret'
    calls = []
    def transport(args, **kwargs):
        calls.append(args)
        assert all(engine.key not in arg for arg in args)
        # Header file is produced by curl; simulate the provider response without real network.
        from pathlib import Path
        Path(args[args.index('--dump-header')+1]).write_text('retry-after: 0\n')
        return SimpleNamespace(returncode=0,stdout='{"error":"private provider detail"}\n'+status)
    monkeypatch.setattr('literaturelab.providers.subprocess.run',transport)
    monkeypatch.setattr('literaturelab.providers.time.sleep',lambda _: None)
    with pytest.raises(ProviderError) as error:
        engine.complete([],Draft)
    assert error.value.status == expected
    assert 'private provider detail' not in str(error.value) and engine.key not in str(error.value)
    assert len(calls) <= 3


def test_output_limit_and_invalid_schema_rejected(monkeypatch):
    engine = Groq(); engine.key = 'gsk_testsecret'
    for reason, content in [('length','{}'),('stop','{"claims":"bad"}')]:
        payload = {'choices':[{'finish_reason':reason,'message':{'content':content}}]}
        monkeypatch.setattr('literaturelab.providers.subprocess.run',lambda *a, **k: SimpleNamespace(returncode=0,stdout=json.dumps(payload)+'\n200'))
        with pytest.raises(ProviderError): engine.complete([],Draft)


def test_transient_groq_schema_generation_failure_retried_without_scoring_answer(monkeypatch):
    engine = Groq(); engine.key = 'gsk_testsecret'
    calls = []
    success = {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(
        {'claims':[],'insufficient_evidence':True,'limitations':['No evidence.']})}}], 'usage':{'total_tokens':20}}
    def transport(*args, **kwargs):
        calls.append(1)
        body = {'error':{'code':'json_validate_failed'}} if len(calls) == 1 else success
        return SimpleNamespace(returncode=0,stdout=json.dumps(body)+'\n'+('400' if len(calls) == 1 else '200'))
    monkeypatch.setattr('literaturelab.providers.subprocess.run',transport)
    monkeypatch.setattr('literaturelab.providers.time.sleep',lambda _:None)
    result, usage = engine.complete([],Draft)
    assert result['insufficient_evidence'] and len(calls) == 2
    assert usage['transport_attempts'] == 2 and usage['schema_failures_retried'] == 1
