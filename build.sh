#!/bin/bash

docker kill dronecapture 
docker rm dronecapture
docker build . -t sabbour/dronecapture 
docker push sabbour/dronecapture
docker run -d -p 1935:1935 -p 8080:8080 --name dronecapture sabbour/dronecapture
docker logs dronecapture -f