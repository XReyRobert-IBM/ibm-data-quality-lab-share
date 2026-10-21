SELECT "LAB_ROW_ID", "client_name" FROM "{{SCHEMA}}"."DQ_V2_CLIENTS_20261015" WHERE "client_name" IS NULL OR TRIM("client_name") = '' OR REGEXP_LIKE("client_name", '\A[\s\p{Z}]*\z');
