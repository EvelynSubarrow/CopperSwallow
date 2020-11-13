FROM python:3.8-slim-buster
COPY requirements.txt /tmp/
RUN pip3 install -r /tmp/requirements.txt
WORKDIR /opt/copperswallow/
COPY . ./
EXPOSE 36323
CMD ["python3", "app.py"]
