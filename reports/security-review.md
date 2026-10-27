# Security and dependency review

Reviewed 27 October 2026 for the local, single-user LiteratureLab system. This is a focused source/dependency review and regression check, not a penetration test or a certification that the application is vulnerability-free.

## Changes made

The initial virtual environment inherited the machine's global Python packages. That introduced unrelated dependency conflicts and old web/upload libraries. The runtime is now isolated (`include-system-site-packages = false`) and contains only the resolved 48-package application/test dependency closure, plus its installation tools. Global Python packages were not changed.

| Dependency | Initial version | Verified installed version |
|---|---:|---:|
| FastAPI | 0.115.0 | 0.162.0 |
| Starlette | 0.38.6 | 1.10.0 |
| python-multipart | 0.0.12 | 0.0.32 |
| AnyIO | 4.13.0 | 4.15.1 |
| certifi | 2026.5.20 | 2026.10.23 |
| urllib3 | 2.7.0 | 2.8.0 |
| fsspec | 2026.2.0 | 2026.9.0 |
| filelock | 3.29.0 | 4.2.4 |
| python-dotenv | 1.0.1 | 1.2.4 |
| FastEmbed | 0.8.0 | 0.9.1 |
| Pillow | 10.4.0 | 13.0.0 |
| Playwright | 1.49.1 | 1.64.1 |

Required supporting dependencies were also resolved and pinned, including typing-extensions 4.16.0, annotated-doc 0.0.5, opentelemetry-api 1.45.1, pyee 13.0.1 and greenlet 3.5.6. Exact observed versions for the full Windows/Python 3.12 closure are recorded in `requirements.txt`. These are version pins, not a cross-platform or hash-locked dependency solution.

Selected wheels were obtained from official [PyPI metadata](https://pypi.org/) and `files.pythonhosted.org`. Every downloaded wheel's SHA-256 was checked against its PyPI metadata before offline installation. The installed environment was assembled from existing installed distributions plus the verified update wheels because this machine blocks Python/pip outbound sockets while Windows curl works. `reports/dependency-wheel-hashes.json` records the downloaded wheel hashes; it is not a complete fresh-install wheelhouse or a hash lock for the packages copied from the machine.

Pillow 12.3.0 was an intermediate compatible update but remained affected by decoder advisories fixed in 13.0.0. FastEmbed 0.8.0 required Pillow below 13. Rather than forcing an incompatible pin, the implementation was updated to FastEmbed 0.9.1, whose published dependency range permits Pillow below 14. The updated text embedding path reproduced three existing indexed vectors with **maximum absolute difference 0**, so that small compatibility check found no vector drift. It does not prove equivalence for every input. The application does not add image upload or Pillow image-decoding features.

The Playwright update addresses a browser-test driver incompatibility with the installed modern Edge browser. Browser test results are reported separately by the browser reviewer.

## Vulnerability database check

The final 48 installed app/test package versions were submitted to the public [OSV query API](https://google.github.io/osv.dev/api/#tag/query/operation/querybatch). **The response listed no vulnerability IDs for any of those 48 versions at the time checked.** The exact package/version list and raw ID results are in `reports/dependency-audit.json`.

This result is limited to the database's known Python-package advisories. It does not cover undisclosed vulnerabilities, application-specific logic errors, Windows/Edge/curl, embedded native components, browser availability, or all possible indirect exploit paths. It is not equivalent to a penetration test or an assurance that every dependency is safe.

## Source review

Reviewed the Python API, corpus, and Groq boundaries and browser rendering without reading the secret `.env` contents.

- **Credential handling:** the provider endpoint is fixed to HTTPS Groq; the key is passed to curl through stdin rather than process arguments. API status returns configuration presence, not the key. Provider error bodies are replaced with user-safe errors. `.env` is ignored and there is no route serving it. A pattern scan found no live-key-shaped `gsk_` string in staged Python, JavaScript, HTML, CSS, test, or script source. The key pasted into chat should still be replaced before sharing the project.
- **Local access boundary:** the documented launcher binds to `127.0.0.1`; Host validation and same-origin checks prevent ordinary browser cross-origin changes and DNS-rebinding host substitutions. There is no multi-user authentication. Other trusted local processes can use the API, so the server must not be exposed as a hosted or LAN service without a separate access-control design.
- **Input and storage:** SQL values are parameterized. PDF paths use document hashes rather than upload names. Inputs have byte, PDF-page, text and query limits. Model output is schema-validated and displayed using text nodes. Claim reference IDs, source span IDs and supporting text are checked locally; model support review is an additional fallible check.
- **Body-length finding:** the first middleware implementation relied on a declared Content-Length while allowing it to be missing. A chunked multipart request could therefore reach parsing before the upload read cap. This was reported to the integration owner, who added a missing-length rejection for POST requests and a regression test. The final staged API tests pass under the updated environment.

## Verification performed

Using the isolated Desktop `.venv` interpreter:

```text
python -m pip check
No broken requirements found.

python -m pytest <final staged tests> -q
24 passed, 1 warning
```

The remaining warning is Starlette's test-client deprecation notice for `httpx`, suggesting its optional `httpx2` testing integration. It did not fail a request or regression test; no warning suppression was added. The integration owner should rerun the full final suite after all agents' edits are synchronized.

## Remaining limits

The application handles untrusted PDFs in the main local process. File/page limits do not establish protection against every decompression bomb or native parser resource-exhaustion input. Use trusted literature for this system; process isolation and stricter resource budgets are required before opening upload access to other users.

Notes, papers, vectors and the `.env` are local plaintext files. The Desktop is the user's chosen OneDrive-backed location, so its normal sync/access settings apply. No hosted deployment, encryption-at-rest system, identity provider or remote access was introduced. Selected source evidence is intentionally sent to Groq for generation/review, as disclosed in the interface.

Section extraction and LLM review remain research-quality limitations. Valid references and copied source spans are not a guarantee of scientific entailment; the live literature evaluation and human inspection of citations remain necessary.
