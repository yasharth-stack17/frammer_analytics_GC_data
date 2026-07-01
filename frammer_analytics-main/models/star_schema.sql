"""
So this is what I understood about star schema sql , it basically defines
the structures of our tables in duckdb database, here we create dimension and
fact tables and find the datatypes of each column . It is basically a blueprint
of our data
"""
-- fact first dim next approach

-- drop existing tables if they exist to avoid conflicts when running the script multiple times

DROP TABLE IF EXISTS fact_video;
DROP TABLE IF EXISTS dim_user;
DROP TABLE IF EXISTS dim_channel;
DROP TABLE IF EXISTS dim_input_type;
DROP TABLE IF EXISTS dim_output_type;
DROP TABLE IF EXISTS dim_language;
DROP TABLE IF EXISTS dim_date;


-- dim tables

-- DIM_USER
-- Who uploaded the content
CREATE TABLE dim_user (
    user_id         INTEGER PRIMARY KEY,
    user_name       VARCHAR NOT NULL,
    is_qa_account   BOOLEAN DEFAULT FALSE    -- flag for QA/test accounts
);

-- DIM_CHANNEL
-- Which workspace/channel
CREATE TABLE dim_channel (
    channel_id      INTEGER PRIMARY KEY,
    channel_name    VARCHAR NOT NULL
);

-- DIM_INPUT_TYPE
-- What kind of content was uploaded
-- interview, speech, debate, news bulletin etc.
CREATE TABLE dim_input_type (
    input_type_id   INTEGER PRIMARY KEY,
    input_type_name VARCHAR NOT NULL
);

-- DIM_OUTPUT_TYPE
-- What format was generated
-- reels, shorts, chapters, summary etc.
CREATE TABLE dim_output_type (
    output_type_id   INTEGER PRIMARY KEY,
    output_type_name VARCHAR NOT NULL
);

-- DIM_LANGUAGE
-- What language the content is in
CREATE TABLE dim_language (
    language_id     INTEGER PRIMARY KEY,
    language_name   VARCHAR NOT NULL
);

-- DIM_DATE
-- When the activity happened
CREATE TABLE dim_date (
    date_id         INTEGER PRIMARY KEY,
    month           VARCHAR NOT NULL,
    year            INTEGER NOT NULL,
    month_number    INTEGER,            -- 1-12 for sorting
    quarter         INTEGER             -- Q1, Q2, Q3, Q4
);


--fact table

-- FACT_VIDEO
-- Central table — all measurements + foreign keys
CREATE TABLE fact_video (

    -- Primary Key
    fact_id             INTEGER PRIMARY KEY,

    -- Foreign Keys → linking to DIM tables
    user_id             INTEGER REFERENCES dim_user(user_id),
    channel_id          INTEGER REFERENCES dim_channel(channel_id),
    input_type_id       INTEGER REFERENCES dim_input_type(input_type_id),
    output_type_id      INTEGER REFERENCES dim_output_type(output_type_id),
    language_id         INTEGER REFERENCES dim_language(language_id),
    date_id             INTEGER REFERENCES dim_date(date_id),

    -- Video identifiers
    video_id            VARCHAR,
    headline            VARCHAR,

    -- Measurable counts
    uploaded_count      INTEGER DEFAULT 0,
    created_count       INTEGER DEFAULT 0,
    published_count     INTEGER DEFAULT 0,

    -- Measurable durations (stored in minutes)
    uploaded_mins       FLOAT DEFAULT 0.0,
    created_mins        FLOAT DEFAULT 0.0,
    published_mins      FLOAT DEFAULT 0.0,

    -- Publishing info
    is_published        BOOLEAN DEFAULT FALSE,
    published_platform  VARCHAR DEFAULT 'Not Published',
    published_url       VARCHAR,

    -- Team info
    team_name           VARCHAR,
    team_name_quality   VARCHAR,        -- Valid or Missing

    -- Derived KPIs (computed during EDA of my two datasets, you can add the ones you find)
    publish_rate        FLOAT,          -- published / created * 100
    multiplication_ratio FLOAT,         -- created / uploaded
    unpublished_gap     INTEGER         -- created - published
);


-- indexes to speed up queries on common filter/join columns

CREATE INDEX idx_fact_user        ON fact_video(user_id);
CREATE INDEX idx_fact_channel     ON fact_video(channel_id);
CREATE INDEX idx_fact_input_type  ON fact_video(input_type_id);
CREATE INDEX idx_fact_output_type ON fact_video(output_type_id);
CREATE INDEX idx_fact_language    ON fact_video(language_id);
CREATE INDEX idx_fact_date        ON fact_video(date_id);
CREATE INDEX idx_fact_published   ON fact_video(is_published);