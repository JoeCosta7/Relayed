CREATE DATABASE "Relayed_test";
CREATE USER test_user WITH PASSWORD 'test_password';
GRANT CONNECT ON DATABASE "Relayed_test" TO test_user;
\c "Relayed_test"
GRANT USAGE, CREATE ON SCHEMA public TO test_user;