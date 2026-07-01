#!/bin/bash

python3 -u create_query_list.py $1 && \
python3 -u request_by_inchikey.py && \
python3 -u modify_massbank_data.py $1 false

python3 -u create_query_list.py $1 && \
python3 -u request.py $2 && \
python3 -u modify_massbank_data.py $1 false
