"""SYNTHETIC hand-calculated dashboard data. Never used by production code."""
from dataclasses import replace
import os
from pathlib import Path
import re

from src.dashboard.service import DatabaseConfig


SQL_ROOT = Path(__file__).resolve().parents[1] / 'src' / 'sql'


def test_config():
    name = os.environ.get('OULAD_DASHBOARD_TEST_DATABASE', '')
    if not re.fullmatch(r'oulad_test_dashboard(?:_[A-Za-z0-9]+)*', name):
        raise ValueError('Refusing destructive tests outside oulad_test_dashboard[_suffix]')
    return replace(DatabaseConfig.from_env(), database=name)


def seed(conn):
    # Validate BOTH opt-in target and live connection before any destructive SQL.
    config = test_config()
    if conn.execute('SELECT current_database()').fetchone()[0] != config.database:
        raise ValueError('Refusing destructive tests on a different live database')
    conn.execute('DROP SCHEMA IF EXISTS dw CASCADE; DROP SCHEMA IF EXISTS etl CASCADE;')
    conn.execute((SQL_ROOT / '01_ddl_dw.sql').read_text(encoding='utf-8'))
    conn.execute((SQL_ROOT / 'etl' / '00_bootstrap_log.sql').read_text(encoding='utf-8'))
    conn.execute("""
        INSERT INTO dw.dim_offering VALUES
        (1,'AAA','STEM','2014J',2014,10,9,2),
        (2,'AAA','STEM','2013J',2013,10,14,2),
        (3,'BBB','Social Sciences','2014J',2014,10,56,8),
        (4,'CCC','STEM','2014J',2014,10,1,1);
        INSERT INTO dw.dim_day
        SELECT n,n,floor(n/7.0),floor(n/28.0),CASE WHEN n<0 THEN 'Before start' ELSE 'After start' END
        FROM generate_series(-100,100) n;
        INSERT INTO dw.dim_day VALUES (-9999,NULL,NULL,NULL,'Unknown'),(-9998,NULL,NULL,NULL,'Not applicable');
        INSERT INTO dw.dim_result VALUES
        (1,'Pass','Successful',false,1),(2,'Distinction','Successful',false,2),
        (3,'Fail','At risk',true,3),(4,'Withdrawn','At risk',true,4);
        INSERT INTO dw.dim_student VALUES
        (1,101,1,'M','Region','A Level','10-20%',2,'0-35','N','2013J','2014J',false),
        (2,101,2,'M','Region','A Level','10-20%',2,'35-55','N','2014J','2014J',true),
        (3,102,1,'F','Region','No Formal','Unknown',NULL,'0-35','Y','2014J','2014J',true),
        (4,103,1,'M','Region','HE','20-30%',3,'0-35','N','2014J','2014J',true),
        (5,104,1,'F','Region','A Level','10-20%',2,'0-35','N','2014J','2014J',true);
        INSERT INTO dw.dim_student
        SELECT n,99+n,1,'M','Region','A Level','Unknown',NULL,'0-35','N','2014J','2014J',true
        FROM generate_series(6,9) n;
        INSERT INTO dw.fact_enrollment
        (student_key,offering_key,result_key,registration_day_key,unregistration_day_key,
         first_active_day_key,last_active_day_key,studied_credits,num_prev_attempts,total_clicks,active_days,
         submitted_count,banked_count,has_status_conflict)
        VALUES
        (1,1,1,-90,-9998,-9998,-9998,60,0,6,1,0,0,false),
        (2,2,2,-30,-9998,0,0,60,1,4,1,0,0,false),
        (3,1,3,0,6,1,1,60,2,7,1,0,0,true),
        (4,1,4,-1,-9999,2,2,60,0,10,1,0,1,true),
        (5,3,3,28,84,50,50,60,0,3,1,0,0,true),
        (6,1,4,-89,0,-9998,-9998,60,1,0,0,0,0,false),
        (7,1,1,-29,28,10,10,60,0,1,1,0,0,false),
        (8,1,4,-9999,-1,-9998,-9998,60,2,0,0,0,0,false),
        (9,1,1,-31,27,3,10,60,0,3,2,0,0,false);
        INSERT INTO dw.dim_assessment VALUES
        (1,11,1,'TMA',50,3,3,false,false,true),
        (2,12,1,'CMA',0,7,7,false,true,true),
        (3,13,1,'Exam',100,NULL,9,true,false,false),
        (4,14,2,'TMA',100,5,5,false,false,true),
        (5,15,4,'Exam',100,NULL,0,true,false,false),
        (6,16,3,'Exam',100,55,55,false,false,true);
        INSERT INTO dw.fact_assessment VALUES
        (1,1,1,3,0,0,0,false,false,false),
        (3,1,1,4,NULL,NULL,1,true,false,false),
        (4,1,1,-9998,80,40,NULL,NULL,true,false),
        (1,1,2,8,100,0,1,true,false,false),
        (2,2,4,5,60,60,0,false,false,false),
        (5,3,6,55,20,20,NULL,NULL,false,false);
        INSERT INTO dw.dim_vle_site VALUES
        (1,101,1,'oucontent','Content',NULL,NULL),
        (2,102,1,'forumng','Collaboration',NULL,NULL),
        (3,103,2,'oucontent','Content',NULL,NULL),
        (4,104,3,'quiz','Assessment',NULL,NULL);
        INSERT INTO dw.fact_vle_daily VALUES
        (1,1,1,7,6,1,false),(2,2,3,0,4,1,false),(3,1,1,1,7,1,false),
        (4,1,2,2,10,1,false),(9,1,1,3,2,1,false),(5,3,4,50,3,1,false),
        (7,1,1,10,1,1,false),(9,1,1,10,1,1,false);
        INSERT INTO dw.fact_student_week VALUES
        (1,1,6,0,0,0,0,NULL,1,1,0,0),
        (2,2,6,4,1,4,1,6,0,1,1,NULL),
        (4,1,6,10,1,10,1,4,0,2,2,NULL),
        (7,1,6,0,0,0,0,NULL,0,1,1,NULL),
        (9,1,6,2,1,2,1,3,1,1,0,NULL),
        (1,1,13,6,1,6,1,6,2,3,1,50),
        (2,2,13,0,0,4,1,13,1,1,0,60),
        (4,1,13,0,0,10,1,11,0,2,2,NULL),
        (7,1,13,1,1,1,1,3,0,2,2,NULL),
        (9,1,13,1,1,3,2,3,1,1,0,NULL),
        (5,3,55,3,1,3,1,5,1,2,1,20);
        REFRESH MATERIALIZED VIEW dw.agg_vle_offering_week_activity;
        -- Synthetic gate state for SQL/UI tests, NOT a full-OULAD acceptance run.
        INSERT INTO etl.run(status,finished_at) VALUES ('SUCCESS',now());
    """)
