import httpx
import json

url = "http://127.0.0.1:8000/api/rag/ask/upload"
files = [
    ("files", ("arquitectura_rag.drawio", open("TestFiles/arquitectura_rag.drawio","rb"), "application/xml")),
    ("files", ("diccionario_datos.xlsx", open("TestFiles/diccionario_datos.xlsx","rb"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
]

data = {
    'query': '¿Qué muestra el diagrama sobre la arquitectura?',
    'top_k': '5',
    'max_new_tokens': '200',
    'temperature': '0.2',
    'conversation_history': json.dumps([{"user":"Hola","assistant":"Hola"}]),
}

with httpx.Client(timeout=60.0) as client:
    resp = client.post(url, data=data, files=files)
    print('status', resp.status_code)
    try:
        print(resp.json())
    except Exception:
        print(resp.text)
