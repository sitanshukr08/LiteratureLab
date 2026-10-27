import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, UploadFile, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .core import Corpus, InputError
from .synthesis import Synthesis, ProviderError

ROOT = Path(__file__).resolve().parents[1]


class Query(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    question: str = Field(min_length=1, max_length=1200, pattern=r'.*\S.*')
    paper_ids: list[str] = Field(default_factory=list, max_length=30)
    strategy: Literal['dense','hybrid','adaptive'] = 'adaptive'
    refresh: bool = False
    provider: Literal['auto','gemini','groq'] | None = None


def create_app(corpus=None):
    app = FastAPI(title='LiteratureLab', version='0.2.0', docs_url='/api/docs', redoc_url=None)
    library = corpus or Corpus(ROOT / 'data')
    engine = Synthesis(library)
    app.state.corpus, app.state.engine = library, engine
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1','localhost','[::1]'])

    @app.middleware('http')
    async def boundaries(request: Request, call_next):
        origin = request.headers.get('origin')
        if request.method in {'POST','DELETE','PUT','PATCH'} and origin:
            parsed = urlparse(origin)
            if parsed.scheme != request.url.scheme or parsed.netloc != request.headers.get('host'):
                return JSONResponse({'error':'Cross-origin changes are not allowed.'}, status_code=403)
        if request.method == 'POST' and 'content-length' not in request.headers:
            return JSONResponse({'error':'A bounded Content-Length is required for uploads and queries.'}, status_code=411)
        length = request.headers.get('content-length', '0')
        if not length.isdigit() or int(length) > 21 * 1024**2:
            return JSONResponse({'error':'Request is too large.'}, status_code=413)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        response.headers['Cache-Control'] = 'no-store' if request.url.path.startswith('/api/') else 'no-cache'
        return response

    @app.exception_handler(InputError)
    async def input_error(request, exc):
        return JSONResponse({'error':str(exc)}, status_code=400)

    @app.exception_handler(ProviderError)
    async def provider_error(request, exc):
        return JSONResponse({'error':str(exc)}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({'error':'Check the question, paper selection and retrieval strategy.'}, status_code=422)

    @app.get('/api/status')
    def status():
        return {'name':'LiteratureLab','model':engine.provider.model,'key_configured':any(p['key_configured'] for p in engine.provider.providers_status()),
                'papers':len(library.papers()),'embeddings_ready':(ROOT / 'models/bge/model_optimized.onnx').exists(),
                'generation':'Gemini / Groq API','providers':engine.provider.providers_status(),
                'default_provider':engine.provider.preference,'retrieval':'Local CPU / BGE + BM25', 'version':'0.2.0'}

    @app.get('/api/papers')
    def papers():
        return library.papers()

    @app.post('/api/papers')
    def upload(file: UploadFile):
        data = file.file.read(20 * 1024**2 + 1)
        return library.ingest(data, file.filename or 'paper.pdf')

    @app.delete('/api/papers/{paper_id}')
    def remove(paper_id: str):
        library.delete(paper_id)
        return {'deleted':paper_id}

    @app.get('/api/papers/{paper_id}/pdf')
    def pdf(paper_id: str):
        paper = next((p for p in library.papers() if p['id'] == paper_id), None)
        if paper is None:
            raise HTTPException(404, 'Paper not found')
        return FileResponse(library.root / 'pdfs' / f'{paper_id}.pdf', media_type='application/pdf', content_disposition_type='inline', filename=paper['filename'])

    @app.post('/api/search')
    def search(query: Query):
        return library.search(query.question, query.paper_ids, query.strategy)

    @app.post('/api/ask')
    def ask(query: Query):
        return engine.ask(query.question, query.paper_ids, query.strategy, query.refresh, provider=query.provider)

    @app.get('/api/history')
    def history():
        with library.db() as db:
            rows = db.execute('SELECT id,created,result FROM history ORDER BY created DESC LIMIT 50').fetchall()
        return [{'id':r[0], 'created':r[1], 'question':json.loads(r[2])['question']} for r in rows]

    @app.get('/api/history/{entry_id}')
    def history_item(entry_id: str):
        with library.db() as db:
            row = db.execute('SELECT result FROM history WHERE id=?', (entry_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Research note not found')
        return json.loads(row[0])

    @app.get('/api/evaluation')
    def evaluation():
        path = ROOT / 'reports/evaluation.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'status':'not-run'}

    @app.get('/')
    def index():
        return FileResponse(ROOT / 'web/index.html')

    app.mount('/assets', StaticFiles(directory=ROOT / 'web', check_dir=False), name='assets')
    return app


app = create_app()
