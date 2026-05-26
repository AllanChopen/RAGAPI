import httpx
import json

url = "http://127.0.0.1:8000/api/rag/ask/upload"
files = [
    ("files", ("diccionario_datos.xlsx", open("TestFiles/diccionario_datos.xlsx","rb"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
]

data = {
    'query': 'que campos hay en el diccionario?',
    'top_k': '5',
    'max_new_tokens': '200',
    'temperature': '0.2',
    'conversation_history': json.dumps([]),
    'sources': 'uploaded,repo,api',
    'keep_uploaded': 'true'
}

with httpx.Client(timeout=60.0) as client:
    resp = client.post(url, data=data, files=files)
    print('status', resp.status_code)
    try:
        print(resp.json())
    except Exception:
        print(resp.text)
