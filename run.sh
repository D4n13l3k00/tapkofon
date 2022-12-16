#!/bin/bash

cd tapkofon
../.env/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8888
cd ..
