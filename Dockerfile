FROM python:3.10

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN pip install gunicorn
COPY deaddit deaddit
EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "deaddit:app"]
