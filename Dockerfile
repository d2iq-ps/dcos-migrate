FROM python:3.8.6

WORKDIR /workdir
ADD ./ /workdir
RUN pip install .
ENTRYPOINT ["/usr/local/bin/dcos-migrate"]
