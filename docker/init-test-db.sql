SELECT 'CREATE DATABASE focusradio_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'focusradio_test')\gexec
