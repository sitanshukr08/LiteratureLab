"""Real-browser checks for provider controls; hosted inference is always intercepted.

Retrieval, paper/history reads, PDF serving and export use the real local app.
Answer/provider/error rendering uses a previously recorded result as a fixture.
This verifies browser behavior, not provider availability or answer accuracy.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8766')
    args = parser.parse_args()
    reports = ROOT / 'reports'
    report_path = reports / 'browser-provider-check.json'
    fixture = json.loads((reports / 'paper-evaluation/pilot/vt02.json').read_text(encoding='utf-8'))['result']
    report = {'created': datetime.now(timezone.utc).isoformat(), 'url': args.url,
              'browser': 'Isolated headless Microsoft Edge via Playwright',
              'live_model_calls': 0, 'checks': [], 'console_errors': [], 'page_errors': [],
              'unexpected_http_errors': [], 'expected_rejections': [], 'mocked_answer_requests': []}
    mode = 'success'
    busy_checks = []

    def check(name, details=None, mocked=False):
        item = {'name': name, 'passed': True, 'mocked_generation': mocked}
        if details is not None:
            item['details'] = details
        report['checks'].append(item)
        print(json.dumps(item), flush=True)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
            page = context.new_page()
            page.on('pageerror', lambda error: report['page_errors'].append(str(error)))

            def console(message):
                if message.type == 'error' and '429' not in message.text:
                    report['console_errors'].append(message.text)

            def response(response):
                if response.status < 400:
                    return
                item = {'url': response.url, 'status': response.status}
                if response.status == 429 and response.url.endswith('/api/ask'):
                    report['expected_rejections'].append(item)
                else:
                    report['unexpected_http_errors'].append(item)

            page.on('console', console)
            page.on('response', response)

            def mocked_answer(route):
                body = route.request.post_data_json
                report['mocked_answer_requests'].append({'provider': body['provider'], 'question': body['question']})
                busy_checks.append(all(page.locator('#' + name).is_disabled()
                                       for name in ['ask', 'retrieve', 'upload', 'provider', 'strategy']))
                if mode == 'quota':
                    route.fulfill(status=429, content_type='application/json',
                                  body=json.dumps({'error': 'Simulated provider quota reached. Retry later.'}))
                    return
                result = deepcopy(fixture)
                result['question'] = body['question']
                if body['provider'] != 'auto':
                    result['provider'] = body['provider']
                    result['model'] = body['provider'] + '-browser-fixture'
                    result['provider_attempts'] = [{'provider': body['provider'], 'outcome': 'completed'}]
                if mode == 'malicious':
                    result['claims'][0]['text'] = '<img src=x onerror="window.fixtureInjected=true"> literal source text'
                route.fulfill(status=200, content_type='application/json', body=json.dumps(result))

            # No UI action below can reach a hosted model, including accidental submissions.
            page.route('**/api/ask', mocked_answer)
            page.goto(args.url, wait_until='networkidle')
            expect(page.locator('.paper')).to_have_count(1)
            expect(page.locator('.paper-info')).to_contain_text('43 pages')
            expect(page.locator('#connection')).to_contain_text('Gemini + Groq configured')
            status = context.request.get(args.url + '/api/status').json()
            assert len(status['providers']) == 2 and all(p['key_configured'] for p in status['providers'])
            assert all(set(p) == {'name', 'model', 'key_configured'} for p in status['providers'])
            check('One real 43-page paper and two provider configuration indicators; public metadata only')
            assert page.locator('#provider option').evaluate_all('(options) => options.map(o => o.value)') == ['auto', 'gemini', 'groq']
            assert page.locator('label[for="provider"]').count() == 1
            check('Provider choices have an associated visible label')
            page.keyboard.press('Tab')
            expect(page.locator('.skip')).to_be_focused()
            page.keyboard.press('Enter')
            expect(page.locator('#question')).to_be_focused()
            check('Keyboard skip link reaches the question')

            page.locator('.paper input').check()
            page.locator('#question').fill('whats this paper about explain it like im new to this')
            with page.expect_response(lambda r: r.url.endswith('/api/search')) as response_info:
                page.locator('#retrieve').click()
            retrieval = response_info.value.json()
            assert response_info.value.status == 200 and retrieval['evidence']
            assert retrieval['trace']['structural_prior'] == 'overview'
            assert retrieval['evidence'][0]['section'].casefold() == 'abstract'
            expect(page.locator('#error')).to_be_hidden()
            expect(page.locator('#retrieve')).to_be_enabled()
            check('Casual punctuation-free question uses real local retrieval and retrieves the abstract first',
                  {'evidence': len(retrieval['evidence']), 'retrieval_ms': retrieval['trace']['total_ms']})

            # History can change while the independent live evaluation runs; choose one with citations.
            notes = context.request.get(args.url + '/api/history').json()
            saved = next(note for note in notes
                         if context.request.get(args.url + '/api/history/' + note['id']).json()['claims'])
            page.locator('#history button').filter(has_text=saved['question']).first.click()
            expect(page.locator('#answer-section')).to_be_visible()
            expect(page.locator('.citation').first).to_be_visible()
            check('Previously saved real answer opens without inference')

            for provider in ['auto', 'gemini', 'groq']:
                page.locator('#provider').select_option(provider)
                page.locator('#question').fill('can u explain this in normal words')
                page.locator('#ask').click()
                expect(page.locator('#research-status')).to_contain_text('Synthesis complete')
                expect(page.locator('#answer-title')).to_have_text('Answer from your papers')
                assert report['mocked_answer_requests'][-1]['provider'] == provider
            check('Auto and both manual provider selections reach request payloads; answer rendering succeeds', mocked=True)
            assert busy_checks and all(busy_checks)
            check('Question actions and provider controls are disabled while a request is pending', mocked=True)

            ref = fixture['claims'][0]['evidence'][0]
            page.locator('.citation').first.click()
            source = page.locator('#source-' + ref['id'])
            assert source.locator('details').get_attribute('open') is not None
            assert source.locator('a').get_attribute('href').endswith('#page=' + str(ref['pages'][0]))
            pdf = context.request.get(args.url + f"/api/papers/{ref['paper_id']}/pdf")
            assert pdf.status == 200 and pdf.body().startswith(b'%PDF')
            check('Citation opens its exact evidence card and page link; original PDF is served', mocked=True)
            with page.expect_download() as download_info:
                page.locator('#export').click()
            exported = Path(download_info.value.path()).read_text(encoding='utf-8')
            assert ref['quote'] in exported and 'Provider: groq' in exported
            check('Export includes provider metadata and exact source quotation', mocked=True)
            page.screenshot(path=str(reports / 'browser-provider-desktop.png'), full_page=True)

            mode = 'quota'
            page.locator('#ask').click()
            expect(page.locator('#error')).to_contain_text('Simulated provider quota reached')
            expect(page.locator('#answer-section')).to_be_hidden()
            expect(page.locator('#provider')).to_be_enabled()
            expect(page.locator('#ask')).to_be_enabled()
            check('Simulated quota failure hides stale answer and restores controls', mocked=True)

            mode = 'malicious'
            page.locator('#ask').click()
            expect(page.locator('#research-status')).to_contain_text('Synthesis complete')
            expect(page.locator('#answer-content')).to_contain_text('<img src=x')
            assert page.locator('#answer-content img').count() == 0
            assert page.evaluate('typeof window.fixtureInjected') == 'undefined'
            check('Untrusted model text is rendered literally and cannot insert HTML', mocked=True)

            mode = 'success'
            page.locator('#ask').click()
            expect(page.locator('#research-status')).to_contain_text('Synthesis complete')
            # Screenshots show a genuine stored model answer, not the intercepted fixture.
            notes = context.request.get(args.url + '/api/history').json()
            real_note = next(note for note in notes[:12]
                             if context.request.get(args.url + '/api/history/' + note['id']).json()['claims'])
            page.locator('#history button').filter(has_text=real_note['question']).first.click()
            expect(page.locator('#research-status')).to_have_text('Opened a saved research note.')
            report['screenshot_note_id'] = real_note['id']
            page.screenshot(path=str(reports / 'browser-provider-desktop.png'), full_page=True)
            page.set_viewport_size({'width': 375, 'height': 812})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.screenshot(path=str(reports / 'browser-provider-mobile.png'), full_page=True)
            check('375-pixel layout has no horizontal page overflow', mocked=True)
            assert not report['console_errors'] and not report['page_errors'] and not report['unexpected_http_errors']
            check('No unexpected browser console, JavaScript or HTTP errors')
            browser.close()
        report['passed'] = True
    except Exception as error:
        report['passed'] = False
        report['failure'] = str(error)
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
