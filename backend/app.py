from flask import Flask, request, jsonify
from jinja2 import Template
import os
import together

# ใช้ import ใหม่จาก langchain_community แทนการ import แบบเดิม
from langchain_huggingface import HuggingFaceEmbeddings

from langchain_community.vectorstores import FAISS
import os
import together
from dotenv import load_dotenv

# โหลดค่า environment variables จากไฟล์ .env


# ----- ตั้งค่า API Key และโมเดล -----
# ไม่ต้องเขียน os.environ["TOGETHER_API_KEY"] = "..." ตรงนี้
model_name = "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free"
together.api_key = os.environ.get('TOGETHER_API_KEY')

# จากนี้ไปคุณสามารถใช้งาน together.api_key ได้ตามปกติ

# ----- ตั้งค่า Prompt Template และ Model -----
system_prompt = """ 
You are an experienced veterinarian with a deep understanding of pet behavior and effective behavior correction techniques. Your advice should be clear, professional, and conversational, providing natural and friendly guidance to the pet owner. 

**Important:** Answer in Thai or English only. Do not include any other languages.

Please:
- Understand the pet owner's report and identify the main issues.
- Answer directly if a clear question is asked.
- Provide advice in a friendly, natural tone without being overly formal.
- Keep the final answer succinct and focused solely on addressing the pet owner's concern.
- Ensure your response is entirely in Thai (or English), with no foreign language terms.

### **Final Answer:**
(Provide a clear and natural answer in a friendly tone.)
"""

user_prompt = """Context (Pet owner's report):
{context}
---
Here is the question regarding your pet's behavior:

Question: {question}

### **Instructions:**
1. Identify the main issue from the report.
2. Answer in a natural, friendly tone as if speaking directly to the pet owner.
3. Keep your answer concise and focused solely on the concern.
4. **Important:** Ensure the answer is entirely in Thai or English only. Do not include words from any other language.

---
### **🔹 Response Format**
"""

chat_template_str = """
{% for message in messages %}
{% if message['role'] == 'system' %}
System: {{ message['content'] }}
{% elif message['role'] == 'user' %}
User: {{ message['content'] }}
{% elif message['role'] == 'assistant' %}
Assistant: {{ message['content'] }}
{% endif %}
{% endfor %}
{% if add_generation_prompt %}
Assistant:
{% endif %}
"""
chat_template = Template(chat_template_str)

def generate_chat_prompt(context, question):
    filled_user_prompt = user_prompt.format(context=context, question=question)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": filled_user_prompt},
    ]
    return chat_template.render(messages=messages, add_generation_prompt=True)

# ----- ตั้งค่า API Key และโมเดล -----

def generate_response(model_name, final_prompt):
    response = together.Complete.create(
        model=model_name,
        prompt=final_prompt,
        max_tokens=520,
        temperature=0.1,
        stop=["Assistant:"],
        top_p=0.85
    )
    return response.get("choices", [{}])[0].get("text", "").strip()

# ----- ฟังก์ชันจัดการเอกสารที่ดึงมา -----
def extract_context(retrieved_docs):
    """ดึง matched content จากเอกสารที่ค้นพบมาเป็น context"""
    context = "\n".join([doc.page_content for doc in retrieved_docs])
    return context.strip()

# ----- โหลด Vector Store ด้วย FAISS -----
# ตั้งค่า embeddings โดยใช้โมเดล BAAI/bge-m3from langchain_huggingface import HuggingFaceEmbeddings
embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")
faiss_index = FAISS.load_local(
    r"./faiss_index",  # แก้ไข path ให้ตรงกับตำแหน่งไฟล์ index ของคุณ
    embeddings,
    index_name="index",
    allow_dangerous_deserialization=True
)

# ----- สร้าง Flask App สำหรับ API -----
app = Flask(__name__)

@app.route('/generate', methods=['POST'])
def generate():
    """
    รับ JSON payload ที่มี key 'user_query'
    แล้วใช้ similarity search และโมเดลภาษาในการสร้างคำตอบ
    """
    data = request.get_json()
    if not data or 'user_query' not in data:
        return jsonify({'error': 'No user_query provided'}), 400

    user_query = data['user_query']

    # ดึงเอกสารที่เกี่ยวข้องด้วย similarity search จาก FAISS
    retrieved_docs = faiss_index.similarity_search(query=user_query, k=3)
    context = extract_context(retrieved_docs)

    # สร้าง final prompt ด้วย context ที่ดึงมาและ user_query
    final_prompt = generate_chat_prompt(context, user_query)
    answer = generate_response(model_name, final_prompt)

    return jsonify({'answer': answer})

if __name__ == '__main__':
    # รัน Flask API บนพอร์ต 5000 และให้เชื่อมต่อกับทุก IP (สำหรับ Docker หรือ VM)
    app.run(host='0.0.0.0', port=8087)
