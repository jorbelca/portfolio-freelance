BEGIN;
ALTER TABLE search_document_reads DROP CONSTRAINT search_document_reads_format_check;
ALTER TABLE search_document_reads ADD CONSTRAINT search_document_reads_format_check
 CHECK(format IN ('html','smartrecruiters','greenhouse','lever','legacy'));
COMMIT;
