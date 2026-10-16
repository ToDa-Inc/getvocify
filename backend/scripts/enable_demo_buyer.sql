-- Turns the Demo buyer on for the company of one user (run in the Supabase SQL editor).
-- Only owners/admins of a company with this flag see it in the desktop app and can call /api/v1/demo/*.
INSERT INTO company_feature_flags (company_id, flag, enabled)
SELECT m.company_id, 'DEMO_BUYER_ENABLED', TRUE
FROM company_members m
JOIN auth.users u ON u.id = m.user_id
WHERE u.email = 'itsdanilo.ai@gmail.com'
ON CONFLICT (company_id, flag) DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = NOW();

-- Off again:
-- UPDATE company_feature_flags SET enabled = FALSE WHERE flag = 'DEMO_BUYER_ENABLED';
