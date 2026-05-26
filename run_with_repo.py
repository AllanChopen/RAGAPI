import httpx
import json

url = "http://127.0.0.1:8000/api/rag/ask/upload"
files = [
    ("files", ("diccionario_datos.xlsx", open("TestFiles/diccionario_datos.xlsx","rb"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
]

data = {
    'query': '¿qué tablas hay en el diccionario?',
    'top_k': '5',
    'max_new_tokens': '200',
    'temperature': '0.2',
    'conversation_history': json.dumps([]),
    'sources': 'uploaded,repo,api',
    'keep_uploaded': 'true',
    'repo_url': 'https://github.com/umg-admin-ing/APIBanca'
}

with httpx.Client(timeout=180.0) as client:
    resp = client.post(url, data=data, files=files)
    print('status', resp.status_code)
    try:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(resp.text)
