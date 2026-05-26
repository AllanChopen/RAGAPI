import httpx
import json
import subprocess

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
    'keep_uploaded': 'true'
}

with httpx.Client(timeout=120.0) as client:
    resp = client.post(url, data=data, files=files)
    print('status', resp.status_code)
    try:
        j = resp.json()
        print(json.dumps(j, indent=2, ensure_ascii=False))
    except Exception:
        print(resp.text)

# Now run compute_similarity_uploaded.py to show numeric similarities
print('\n--- Similarities (uploaded chunks) ---')
subprocess.run(["c:/Users/allan/Documents/Python/RAG/.venv/Scripts/python.exe", "compute_similarity_uploaded.py"], check=False)
