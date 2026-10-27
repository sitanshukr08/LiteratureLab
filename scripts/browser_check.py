"""Real, isolated Edge browser checks against a running local LiteratureLab server.

Default checks reuse saved notes and do not call Groq. --synthesize-cached should
only be used after the evaluation has seeded this exact question/model/corpus.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
QUESTION = 'How do RAG-Sequence and RAG-Token differ in their treatment of retrieved documents during generation?'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    parser.add_argument('--synthesize-cached', action='store_true')
    args = parser.parse_args()
    reports = ROOT / 'reports'
    reports.mkdir(exist_ok=True)
    report = {'created': datetime.now(timezone.utc).isoformat(), 'browser': 'Isolated Microsoft Edge (Playwright)',
              'url': args.url, 'checks': [], 'console_errors': [], 'console_warnings': [], 'page_errors': [],
              'failed_requests': [], 'unexpected_http_errors': [], 'expected_rejections': []}
    (reports / 'browser-check.json').write_text(json.dumps({'passed': False, 'status': 'running'}, indent=2), encoding='utf-8')
    expected_invalid_upload = False
    expected_quota_error = False

    def check(name, details=None):
        report['checks'].append({'name': name, 'passed': True, 'details': details})
        print(json.dumps(report['checks'][-1]), flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
        page = context.new_page()
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        page.on('console', lambda message: report['console_errors' if message.type == 'error' else 'console_warnings'].append(message.text)
                if message.type in {'error', 'warning'} else None)
        page.on('requestfailed', lambda request: report['failed_requests'].append({'url': request.url, 'failure': request.failure}))

        def response_check(response):
            if response.status < 400:
                return
            record = {'url': response.url, 'status': response.status}
            if expected_invalid_upload and response.url.endswith('/api/papers') and response.status == 400:
                report['expected_rejections'].append(record)
            elif expected_quota_error and response.url.endswith('/api/ask') and response.status == 429:
                report['expected_rejections'].append(record)
            else:
                report['unexpected_http_errors'].append(record)

        page.on('response', response_check)
        started = time.perf_counter()
        page.goto(args.url, wait_until='networkidle')
        expect(page.locator('.paper')).to_have_count(6)
        expect(page.locator('#connection')).to_contain_text('Groq configured')
        check('Initial library and status', {'papers': 6, 'ready_seconds': round(time.perf_counter() - started, 3)})
        page.screenshot(path=str(reports / 'browser-desktop.png'), full_page=True)
        page.keyboard.press('Tab')
        expect(page.locator('.skip')).to_be_focused()
        page.keyboard.press('Enter')
        expect(page.locator('#question')).to_be_focused()
        check('Keyboard skip link reaches the research question')

        # Exercise the real file input while preserving the already indexed corpus.
        page.locator('#upload').set_input_files(ROOT / 'demo/papers/rag.pdf')
        expect(page.locator('#upload-status')).to_contain_text('already indexed', timeout=20000)
        expect(page.locator('.paper')).to_have_count(6)
        check('Duplicate PDF upload detected without duplicating index')

        expected_invalid_upload = True
        page.locator('#upload').set_input_files({'name': 'invalid.pdf', 'mimeType': 'application/pdf', 'buffer': b'not a PDF'})
        expect(page.locator('#error')).to_contain_text('valid PDF')
        expect(page.locator('#upload-status')).to_contain_text('Upload failed')
        expect(page.locator('#ask')).to_be_enabled()
        expected_invalid_upload = False
        check('Invalid upload rejected and controls recover')

        page.locator('#question').fill(QUESTION)
        page.locator('.paper input').first.check()
        page.locator('#retrieve').click()
        expect(page.locator('#research-status')).to_contain_text('Retrieval complete', timeout=30000)
        expect(page.locator('.evidence-card').first).to_be_visible()
        expect(page.locator('#trace-content')).to_contain_text('1600 words')
        expect(page.locator('#error')).to_be_hidden()
        page.locator('#clear-selection').click()
        assert page.locator('.paper input:checked').count() == 0
        check('Local retrieval, selected source filtering, provenance and performance trace')

        note = page.locator('#history').get_by_role('button', name=QUESTION, exact=True).first
        expect(note).to_be_visible()
        note.click()
        expect(page.locator('#answer-section')).to_be_visible()
        expect(page.locator('.citation').first).to_be_visible()
        page.locator('.citation').first.click()
        target = page.locator('.evidence-card.highlight')
        expect(target).to_have_count(1)
        expect(target.locator('details')).to_have_attribute('open', '')
        check('Saved note, claim citation and original evidence navigation')

        pdf_link = target.locator('a')
        href = pdf_link.get_attribute('href')
        assert '/api/papers/' in href and '/pdf#page=' in href
        with page.expect_popup() as popup_event:
            pdf_link.click()
        popup = popup_event.value
        popup.wait_for_load_state('networkidle')
        assert '/api/papers/' in popup.url and '/pdf' in popup.url
        # Navigate out of Edge's browser-owned PDF viewer before disposing the
        # isolated test context; old drivers can race its extension child target.
        popup.goto('about:blank', wait_until='load')
        popup.close()
        check('Original PDF page opens in a separate tab', {'href': href})

        with page.expect_download() as download_event:
            page.locator('#export').click()
        download = download_event.value
        destination = reports / 'browser-exported-note.md'
        download.save_as(destination)
        assert destination.read_text(encoding='utf-8').startswith('# ' + QUESTION)
        check('Markdown export download')

        if args.synthesize_cached:
            page.locator('#question').fill(QUESTION)
            with page.expect_response(lambda response: response.url.endswith('/api/ask'), timeout=120000) as event:
                page.locator('#ask').click()
            response = event.value
            assert response.status == 200
            result = response.json()
            assert result['cached'] is True, 'Expected seeded cache; a fresh API request occurred.'
            expect(page.locator('#answer-meta')).to_contain_text('Cached answer')
            check('Synthesis uses seeded cache without a new generation', {'result_id': result['id']})

        page.screenshot(path=str(reports / 'browser-answer.png'), full_page=True)

        # Simulate quota exhaustion in the browser transport; this consumes no
        # Groq quota and proves an old answer is not shown for a failed question.
        expected_quota_error = True
        page.route('**/api/ask', lambda route: route.fulfill(status=429, content_type='application/json', body='{"error":"Test quota exhausted. Retry later."}'))
        page.locator('#question').fill('A different question whose request cannot complete.')
        page.locator('#ask').click()
        expect(page.locator('#error')).to_contain_text('Test quota exhausted')
        expect(page.locator('#answer-section')).to_be_hidden()
        expect(page.locator('#ask')).to_be_enabled()
        page.unroute('**/api/ask')
        expected_quota_error = False
        check('Quota failure restores controls and does not display a stale answer')
        note.click()

        page.locator('#evaluation-tab').click()
        expect(page.locator('.eval-table')).to_be_visible()
        expect(page.locator('#evaluation-content')).to_contain_text('Paper coverage')
        check('Evaluation view displays recorded measurements')
        page.locator('#research-tab').click()

        page.set_viewport_size({'width': 375, 'height': 812})
        page.screenshot(path=str(reports / 'browser-mobile.png'), full_page=True)
        overflow = page.evaluate('({scroll:document.documentElement.scrollWidth, viewport:window.innerWidth})')
        assert overflow['scroll'] <= overflow['viewport'] + 1, overflow
        check('375px mobile viewport has no horizontal overflow', overflow)
        labels = page.evaluate('Array.from(document.querySelectorAll("button,input,textarea,select")).filter(el => el.getClientRects().length).map(el => ({tag:el.tagName,name:el.getAttribute("aria-label") || el.labels?.[0]?.textContent || el.textContent || el.getAttribute("title")})).filter(el => !el.name?.trim())')
        assert not labels, labels
        check('Visible form controls have accessible names')

        # Expected bad-upload HTTP 400 can produce a browser resource console entry.
        expected_console = [line for line in report['console_errors'] if any(code in line for code in ['400', '429']) and 'Failed to load resource' in line]
        report['expected_error_console_entries'] = expected_console
        report['console_errors'] = [line for line in report['console_errors'] if line not in expected_console]
        assert not report['console_errors'], report['console_errors']
        assert not report['console_warnings'], report['console_warnings']
        assert not report['page_errors'], report['page_errors']
        assert not report['failed_requests'], report['failed_requests']
        assert not report['unexpected_http_errors'], report['unexpected_http_errors']
        check('No unexpected console, script, request or HTTP failures')
        browser.close()
        report['passed'] = True
        (reports / 'browser-check.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('Browser checks passed. Results in reports/browser-check.json', flush=True)


if __name__ == '__main__':
    main()
