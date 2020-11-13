FROM python:3.8-slim-buster
# It might be more portable to use pytz, but ultimately this expects to be run in a Europe/London TZ
ENV TZ=Europe/London
#RUN apk add --update tzdata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
#RUN rm -rf /var/cache/apk/*
# anyway...
COPY requirements.txt /tmp/
RUN pip3 install -r /tmp/requirements.txt
WORKDIR /opt/copperswallow/
COPY . ./
EXPOSE 36323
CMD ["python3", "app.py"]
