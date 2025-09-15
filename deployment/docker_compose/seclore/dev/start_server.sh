#!/bin/bash

docker-compose -f docker-compose.dev.seclore.yml -p dev_seclore up -d --build --force-recreate