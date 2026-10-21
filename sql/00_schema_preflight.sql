-- After loading the isolated table: verify all 11 exact identifiers and no unintended phone alias.
SELECT COLNO, COLNAME, TYPENAME, LENGTH, NULLS
FROM SYSCAT.COLUMNS
WHERE TABSCHEMA = '{{SCHEMA}}' AND TABNAME = 'DQ_V2_CLIENTS_20261015'
ORDER BY COLNO;

SELECT LAB_ROW_ID, "client_name", HEX("client_name") AS NAME_BYTES,
       "address_line", HEX("address_line") AS ADDRESS_BYTES,
       "contact_email", "contact_phone"
FROM {{SCHEMA}}.DQ_V2_CLIENTS_20261015
WHERE LAB_ROW_ID IN (3,8,12,15,16,90,95,100,160,185,190,195)
ORDER BY LAB_ROW_ID;
