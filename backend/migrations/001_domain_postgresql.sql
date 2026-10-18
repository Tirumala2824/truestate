-- TRUESTATE initial schema. Generated from backend/models.py and repository.py.

CREATE TABLE audit_events (
	id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	data TEXT NOT NULL, 
	PRIMARY KEY (id)
)

;
CREATE INDEX ix_audit_events_user_id ON audit_events (user_id);

CREATE TABLE demo_workspaces (
	user_id VARCHAR NOT NULL, 
	data TEXT NOT NULL, 
	revision INTEGER NOT NULL, 
	PRIMARY KEY (user_id)
)

;

CREATE TABLE organizations (
	id VARCHAR(36) NOT NULL, 
	tenant_id VARCHAR NOT NULL, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (tenant_id)
)

;

CREATE TABLE payment_batches (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE TABLE source_documents (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	source_system VARCHAR, 
	integrity_status VARCHAR, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE TABLE suppliers (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	name VARCHAR NOT NULL, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE TABLE users_and_roles (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	subject VARCHAR NOT NULL, 
	role VARCHAR NOT NULL, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

;

CREATE TABLE account_change_events (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	supplier_id VARCHAR(36), 
	external_event_id VARCHAR, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(supplier_id) REFERENCES suppliers (id)
)

;

CREATE TABLE bank_accounts (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	supplier_id VARCHAR(36), 
	account_identifier VARCHAR, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(supplier_id) REFERENCES suppliers (id)
)

;

CREATE TABLE evidence_claims (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	subject VARCHAR, 
	predicate VARCHAR, 
	value VARCHAR, 
	source_system VARCHAR, 
	source_document_id VARCHAR(36), 
	originating_event_id VARCHAR, 
	derived_from_claim_ids TEXT, 
	observed_at VARCHAR, 
	asserted_at VARCHAR, 
	integrity_verification_status VARCHAR, 
	independent_verification_status VARCHAR, 
	confidentiality_classification VARCHAR, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(source_document_id) REFERENCES source_documents (id)
)

;

CREATE TABLE purchase_orders (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	supplier_id VARCHAR(36), 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(supplier_id) REFERENCES suppliers (id)
)

;

CREATE TABLE trusted_supplier_contacts (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	supplier_id VARCHAR(36) NOT NULL, 
	channel VARCHAR, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(supplier_id) REFERENCES suppliers (id)
)

;

CREATE TABLE evidence_dependencies (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	parent_claim_id VARCHAR(36) NOT NULL, 
	child_claim_id VARCHAR(36) NOT NULL, 
	relation VARCHAR, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(parent_claim_id) REFERENCES evidence_claims (id), 
	FOREIGN KEY(child_claim_id) REFERENCES evidence_claims (id)
)

;

CREATE TABLE invoices (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	supplier_id VARCHAR(36), 
	purchase_order_id VARCHAR(36), 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(supplier_id) REFERENCES suppliers (id), 
	FOREIGN KEY(purchase_order_id) REFERENCES purchase_orders (id)
)

;

CREATE TABLE payments (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	supplier_id VARCHAR(36) NOT NULL, 
	bank_account_id VARCHAR(36), 
	batch_id VARCHAR(36), 
	amount_minor INTEGER NOT NULL, 
	state VARCHAR NOT NULL, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(supplier_id) REFERENCES suppliers (id), 
	FOREIGN KEY(bank_account_id) REFERENCES bank_accounts (id), 
	FOREIGN KEY(batch_id) REFERENCES payment_batches (id)
)

;

CREATE TABLE approval_events (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	payment_id VARCHAR(36), 
	approver_id VARCHAR(36), 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(payment_id) REFERENCES payments (id), 
	FOREIGN KEY(approver_id) REFERENCES users_and_roles (id)
)

;

CREATE TABLE investigation_cases (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	payment_id VARCHAR(36) NOT NULL, 
	status VARCHAR, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(payment_id) REFERENCES payments (id)
)

;

CREATE TABLE invoice_line_items (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	invoice_id VARCHAR(36) NOT NULL, 
	amount_minor INTEGER, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(invoice_id) REFERENCES invoices (id)
)

;

CREATE TABLE agent_runs (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	agent VARCHAR, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(case_id) REFERENCES investigation_cases (id)
)

;

CREATE TABLE containment_actions (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	payment_id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	idempotency_key VARCHAR NOT NULL, 
	state VARCHAR, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(payment_id) REFERENCES payments (id), 
	FOREIGN KEY(case_id) REFERENCES investigation_cases (id), 
	UNIQUE (idempotency_key)
)

;

CREATE TABLE hypotheses (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	status VARCHAR, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(case_id) REFERENCES investigation_cases (id)
)

;

CREATE TABLE policy_decisions (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	allowed INTEGER, 
	policy_id VARCHAR, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(case_id) REFERENCES investigation_cases (id)
)

;

CREATE TABLE verification_requests (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	status VARCHAR, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(case_id) REFERENCES investigation_cases (id)
)

;

CREATE TABLE agent_tool_calls (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	run_id VARCHAR(36) NOT NULL, 
	tool VARCHAR, 
	status VARCHAR, 
	payload TEXT NOT NULL, 
	created_at VARCHAR NOT NULL, 
	updated_at VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(run_id) REFERENCES agent_runs (id)
)

;
