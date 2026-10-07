#!/bin/bash
# Initialize OBOA DDBB, retrying until PostgreSQL is ready.
echo
echo "####################"
echo "Initialize OBOA DDBB"
echo "####################"
while true
do
    echo "Trying to initialize OBOA database..."
    if command -v oboa_init.py >/dev/null 2>&1
    then
        oboa_init.py -y
    else
        oboa_init -y
    fi
    status=$?
    if [ $status -ne 0 ]
    then
        echo "Server is not ready yet..."
        sleep 1
    else
        echo "Database has been initialized... :-)"
        break
    fi
done
