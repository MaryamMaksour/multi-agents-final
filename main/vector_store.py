
# vector_store.py
import uuid

VECTOR_CACHE = {}

def store_vector(vec):
    token = f"vec_{uuid.uuid4().hex[:12]}"
    VECTOR_CACHE[token] = vec
    return token

def get_vector(token):
    return VECTOR_CACHE.get(token)
