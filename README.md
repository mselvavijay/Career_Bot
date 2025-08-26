# **💻Career Bot Project**

**Description:**  
**Career Bot** is a web-based application built with **FastAPI** that provides personalized career guidance and job suggestions. The app integrates multiple APIs including **Mistral LLM**, **OpenRouter**, and **JSearch API** to generate dynamic, context-aware responses for users.

---

## **Features**

- Interactive **Career Bot** powered by **Mistral LLM**  
- Job search integration via **JSearch API**  
- Optional conversational enhancements using **OpenRouter API**  
- Hosted on **AWS EC2**, accessible via public IP (port 8000)  
- Environment configuration via **.env** file for API keys  
- Modular, scalable, and easy to extend  

---

## **Tech Stack**

- **Backend:** Python, FastAPI  
- **AI/LLM Integration:**  
  - **Mistral LLM API** for dynamic responses  
  - **OpenRouter API** for conversational routing  
- **Job Search:** JSearch API  
- **Server:** Uvicorn  
- **Deployment:** AWS EC2 (Ubuntu)  
- **Environment Variables:** `.env`  

---

### **Prerequisites**

- Python 3.9+  
- pip  
- AWS EC2 instance (Ubuntu)  
- Git

---

### **Steps**

1. **Clone the repository**  
   ```bash
   git clone <your-repo-url>
   cd career-bot
2. **Create a virtual environment**
   ```bash
   python -m venv venv
source venv/bin/activate   # Linux/macOS

venv\Scripts\activate      # Windows

3. **Create a .env file in the root folder**
   
   OPENROUTER_API_KEY=your_openrouter_api_key_here
   
   JSEARCH_API_KEY=your_jsearch_api_key_here

5. **Run FastApi App**
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000
6. **Access via EC2 public key**
   http://your-ec2-public-ip:8000
   
   http://107.22.84.10:8000   (This is my Public Key IP which is accessible by everyone to use this bot whih is deployed on AWS)
   (Once I start the instance and run it PS:- this is only for testing)
