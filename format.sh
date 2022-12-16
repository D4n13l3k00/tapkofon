#!/bin/bash

isort --gitignore --profile black .
black .
