FROM python:3.10-slim

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . .

ENV PORT=8080
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ENABLECORS=false
ENV STREAMLIT_SERVER_PORT=$PORT

EXPOSE $PORT

CMD ["streamlit", "run", "app.py", "--server.port", "8080", "--server.headless", "true", "--server.enableCORS", "false"]
