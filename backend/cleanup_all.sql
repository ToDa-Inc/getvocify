-- ============================================
-- COMPLETE DATABASE CLEANUP
-- ============================================
-- ⚠️ WARNING: This will DELETE EVERYTHING in your database!
-- Use this to completely wipe your Supabase project database
-- and start fresh with only Vocify tables.
--
-- Run this in your Supabase SQL Editor
-- ============================================

-- ============================================
-- STEP 1: Drop ALL existing tables
-- ============================================
-- This drops all tables in the public schema
-- (Supabase auth schema is protected, so auth.users stays)

DO $$ 
DECLARE
    r RECORD;
BEGIN
    -- Drop all tables in public schema
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') 
    LOOP
        EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
END $$;

-- ============================================
-- STEP 2: Drop ALL functions
-- ============================================

DO $$ 
DECLARE
    r RECORD;
BEGIN
    -- Drop all functions in public schema
    FOR r IN (
        SELECT proname, oidvectortypes(proargtypes) as args
        FROM pg_proc 
        WHERE pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
    ) 
    LOOP
        EXECUTE 'DROP FUNCTION IF EXISTS public.' || quote_ident(r.proname) || ' CASCADE';
    END LOOP;
END $$;

-- ============================================
-- STEP 3: Drop ALL triggers
-- ============================================
-- Triggers are dropped with tables, but this ensures cleanup

DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT trigger_name, event_object_table 
        FROM information_schema.triggers 
        WHERE trigger_schema = 'public'
    ) 
    LOOP
        EXECUTE 'DROP TRIGGER IF EXISTS ' || quote_ident(r.trigger_name) || 
                ' ON public.' || quote_ident(r.event_object_table) || ' CASCADE';
    END LOOP;
END $$;

-- ============================================
-- STEP 4: Drop ALL policies
-- ============================================

DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT schemaname, tablename, policyname 
        FROM pg_policies 
        WHERE schemaname = 'public'
    ) 
    LOOP
        EXECUTE 'DROP POLICY IF EXISTS ' || quote_ident(r.policyname) || 
                ' ON public.' || quote_ident(r.tablename);
    END LOOP;
END $$;

-- ============================================
-- STEP 5: Drop ALL sequences (if any remain)
-- ============================================

DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT sequence_name 
        FROM information_schema.sequences 
        WHERE sequence_schema = 'public'
    ) 
    LOOP
        EXECUTE 'DROP SEQUENCE IF EXISTS public.' || quote_ident(r.sequence_name) || ' CASCADE';
    END LOOP;
END $$;

-- ============================================
-- STEP 6: Drop ALL views (if any)
-- ============================================

DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT table_name 
        FROM information_schema.views 
        WHERE table_schema = 'public'
    ) 
    LOOP
        EXECUTE 'DROP VIEW IF EXISTS public.' || quote_ident(r.table_name) || ' CASCADE';
    END LOOP;
END $$;

-- ============================================
-- STEP 7: Drop ALL types (if any custom types)
-- ============================================

DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT typname 
        FROM pg_type 
        WHERE typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
        AND typtype = 'c'  -- composite types only
    ) 
    LOOP
        EXECUTE 'DROP TYPE IF EXISTS public.' || quote_ident(r.typname) || ' CASCADE';
    END LOOP;
END $$;

-- ============================================
-- STEP 8: Clean up storage policies (optional)
-- ============================================
-- Uncomment if you want to clean storage policies too

-- DO $$ 
-- DECLARE
--     r RECORD;
-- BEGIN
--     FOR r IN (
--         SELECT name 
--         FROM storage.policies
--     ) 
--     LOOP
--         EXECUTE 'DROP POLICY IF EXISTS ' || quote_ident(r.name) || ' ON storage.objects';
--     END LOOP;
-- END $$;

-- ============================================
-- DONE! Database is now completely clean.
-- ============================================
-- Next: Run schema.sql to create Vocify tables
-- ============================================


