FROM python:3.10

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY deaddit deaddit
COPY app.py .
EXPOSE 5000

CMD ["python", "app.py"]
