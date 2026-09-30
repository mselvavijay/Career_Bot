# Project Architecture Update: Layman's Guide

This document explains exactly what we changed in the Career Bot project, step-by-step, and **why** we made those changes. The goal of these updates was to take a prototype script and turn it into a **production-ready backend**—something you can deploy to AWS and connect to a real database.

---

## 1. Creating `requirements.txt` (The Grocery List)
**What we did:** We created a file that lists all the external packages our project needs (like FastAPI, SQLAlchemy, Requests).
**Why we did it:** Imagine trying to bake a cake without knowing the ingredients. Before this file, if another developer (or a cloud server like AWS) tried to run your code, they wouldn't know which tools to install. `requirements.txt` acts as the official "grocery list" for your project.

## 2. Introducing a Database (Memory)
**What we did:** We added `database.py` and a `models/` folder.
**Why we did it:** In the old version, every time a user asked the bot a question, the bot would answer and immediately "forget" the conversation. 
- **SQLAlchemy** is a tool that lets our Python code talk to a database (like SQLite for local testing, or PostgreSQL for AWS).
- **models.py** is where we drew the "blueprint" of a table called `ChatHistory`. Now, every time someone uses the bot, their input, the extracted interests, and the recommended jobs are safely saved into a long-term memory bank (database).

## 3. Creating "Schemas" (The Bouncer)
**What we did:** We added a `schemas/` folder using a tool called Pydantic.
**Why we did it:** When users send data to our API (like their `user_input`), we need to make sure the data is exactly what we expect. Schemas act like a bouncer at a club. They check the incoming data to ensure it's correct, and they also format the outgoing data (the bot's response) so the frontend always receives perfectly structured information.

## 4. Organizing with "Services" (The Workers)
**What we did:** We moved the code that talks to Mistral AI and JSearch into a `services/` folder.
**Why we did it:** Previously, all the logic was crammed into one place. By moving the AI logic into `llm_service.py` and the job search logic into `jsearch_service.py`, we created dedicated "workers". If the JSearch API changes tomorrow, we only have to update the `jsearch_service.py` worker. The rest of the app doesn't care *how* the worker gets the jobs, just that it brings them back.

## 5. Setting up "Routers" (The Traffic Cops)
**What we did:** We created `routers/career.py`.
**Why we did it:** This is the Traffic Cop of our app. When a request comes in to `/career-bot`, the router:
1. Takes the user's input.
2. Asks the `llm_service` to extract interests and explain the career category.
3. Asks the `jsearch_service` to fetch real jobs.
4. Saves everything to the Database.
5. Returns the final answer to the user.
By keeping this step-by-step recipe in the router, it makes the code incredibly easy to read and manage.

## 6. Cleaning up `app.py` & Removing `main.py`
**What we did:** We deleted `main.py` and made `app.py` extremely short.
**Why we did it:** Before, you had two separate files doing almost the same thing (`main.py` for terminal, `app.py` for the web). This caused a split personality where one file had features the other didn't. We deleted `main.py` so there is only **one source of truth**. Now, `app.py` just starts the server, connects to the database, and hands all the actual work over to the "Traffic Cop" (the router). 

---

### Summary
Your app went from being a messy, single-file script to a **modular, enterprise-grade architecture**. 
- It now has **memory** (Database).
- It is **organized** (Routers and Services).
- It is **safe** (Schemas and Error Handling).
- It is **ready to travel** (Requirements list).
