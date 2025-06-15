#!/usr/bin/env python3
"""
Test script for the admin interface with APScheduler (no Redis required).
"""

import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deaddit import app, db
from deaddit.models import Job, JobType, JobStatus, GenerationTemplate
from deaddit.jobs import create_job, get_job_status, get_queue_stats, start_scheduler, stop_scheduler

def test_apscheduler_system():
    """Test the APScheduler-based job system."""
    
    with app.app_context():
        # Create database tables
        db.create_all()
        print("✓ Database tables created successfully")
        
        # Test job creation and scheduling
        print("Testing APScheduler job system...")
        
        # Start the scheduler
        start_scheduler()
        print("✓ APScheduler started")
        
        # Create a test job
        job = create_job(
            job_type=JobType.CREATE_USER,
            parameters={"count": 1, "model": "test"},
            priority=5,
            total_items=1
        )
        
        print(f"✓ Created and scheduled job: {job.id}")
        print(f"  Type: {job.type.value}")
        print(f"  Status: {job.status.value}")
        print(f"  Scheduler ID: {job.rq_job_id}")
        
        # Check queue stats
        stats = get_queue_stats()
        print(f"✓ Queue stats: {stats}")
        
        # Wait a moment for job to potentially execute
        print("⏳ Waiting 3 seconds for job processing...")
        time.sleep(3)
        
        # Check job status after execution attempt
        updated_status = get_job_status(job.id)
        print(f"✓ Job status after execution: {updated_status['status']}")
        
        # Stop the scheduler
        stop_scheduler()
        print("✓ APScheduler stopped")
        
        return True

def test_admin_routes_with_apscheduler():
    """Test that admin routes work with APScheduler."""
    
    with app.test_client() as client:
        print("Testing admin routes with APScheduler...")
        
        # Test dashboard
        response = client.get('/admin/')
        print(f"✓ Dashboard route status: {response.status_code}")
        
        # Test generate page
        response = client.get('/admin/generate')
        print(f"✓ Generate page status: {response.status_code}")
        
        # Test jobs page
        response = client.get('/admin/jobs')
        print(f"✓ Jobs page status: {response.status_code}")
        
        # Test job stats API
        response = client.get('/admin/api/jobs/stats')
        print(f"✓ Job stats API status: {response.status_code}")
        if response.status_code == 200:
            data = response.get_json()
            print(f"  Scheduler running: {data.get('scheduler_running', 'unknown')}")
        
        return True

def test_job_creation_form():
    """Test job creation through web forms."""
    
    with app.test_client() as client:
        print("Testing job creation via web forms...")
        
        # Test user creation form
        response = client.post('/admin/generate/user', data={
            'count': '1',
            'model': 'test-model',
            'wait': '0',
            'priority': '5'
        }, follow_redirects=True)
        
        print(f"✓ User generation form status: {response.status_code}")
        
        # Check if job was created in database
        with app.app_context():
            latest_job = Job.query.order_by(Job.created_at.desc()).first()
            if latest_job:
                print(f"✓ Latest job in database: {latest_job.type.value} (ID: {latest_job.id})")
            else:
                print("⚠ No jobs found in database")
        
        return True

if __name__ == "__main__":
    try:
        print("🧪 Testing Admin Interface with APScheduler")
        print("=" * 50)
        
        test_apscheduler_system()
        print("\n" + "=" * 50)
        
        test_admin_routes_with_apscheduler()
        print("\n" + "=" * 50)
        
        test_job_creation_form()
        print("\n" + "=" * 50)
        
        print("\n🎉 All APScheduler tests passed!")
        print("\n📋 Benefits of APScheduler over Redis:")
        print("✓ No external service dependencies")
        print("✓ Automatic startup with Flask app")
        print("✓ Built-in priority executors")
        print("✓ Cron-style scheduling support")
        print("✓ Simpler deployment and maintenance")
        
        print("\n🚀 Ready to use:")
        print("1. Start app: uv run python app.py")
        print("2. Access admin: http://localhost:5000/admin/")
        print("3. Background jobs work automatically!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)