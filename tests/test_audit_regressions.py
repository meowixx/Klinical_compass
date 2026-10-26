import json
from datetime import datetime, timedelta
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.models import QuestionnaireVersion, QuestionnaireAssignment, MaxUserBinding
from app.questionnaires import validate_answers, calculate_score
from app.max_bot import next_due_at, handle_message
from app.database import SessionLocal


def test_logout_invalidates_browser_cookie():
    with TestClient(app) as client:
        assert client.post('/api/v1/auth/login',json={'login':'Persent','password':'Admin321'}).status_code==200
        assert client.get('/api/v1/account').status_code==200
        assert client.post('/api/v1/auth/logout').status_code==204
        assert client.get('/api/v1/account').status_code==401

@pytest.mark.parametrize('answer',[True,float('nan'),float('inf'),{},[]])
def test_numeric_answers_reject_invalid_values(answer):
    version=QuestionnaireVersion(questions_json=json.dumps([{'id':'q','type':'number','min':0,'max':10}]))
    with pytest.raises(HTTPException) as exc: validate_answers(version,{'q':answer})
    assert exc.value.status_code==422

def test_diary_has_no_meaningless_total():
    version=QuestionnaireVersion(questions_json=json.dumps([{'id':'sleep','type':'number'}]),scoring_json='{}')
    assert calculate_score(version,{'sleep':8}) is None
    version.scoring_json='{"mode":"sum"}'
    assert calculate_score(version,{'sleep':8})==8

def test_overdue_recurrence_skips_missed_days():
    assignment=QuestionnaireAssignment(schedule_type='daily',due_at=datetime.utcnow()-timedelta(days=10))
    due=next_due_at(assignment)
    assert datetime.utcnow()<due<=datetime.utcnow()+timedelta(days=1)

@pytest.mark.parametrize('status',['stopped','consent_declined'])
def test_stopped_binding_cannot_submit_answers(status,monkeypatch):
    sent=[]
    monkeypatch.setattr('app.max_bot.send_message',lambda *args:sent.append(args))
    with TestClient(app),SessionLocal() as db:
        binding=MaxUserBinding(patient_id='p1',max_user_id='audit',status=status,active_answers_json='{"_mode":"state_message"}')
        handle_message(db,binding,'Test')
        assert not db.new
        assert sent

def test_patient_cannot_access_clinician_endpoints():
    with TestClient(app) as client:
        client.post('/api/v1/auth/login',json={'login':'Doctor','password':'Admin241'})
        for url in ['/api/v1/messages','/api/v1/admin/users','/api/v1/audit']:
            assert client.get(url).status_code==403

def test_other_doctor_cannot_update_tasks_or_read_audit():
    from app.models import User
    from app.security import hash_password
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(User(id='other-doctor',login='other',password_hash=hash_password('AuditOther123!'),name='Other Doctor',role='doctor'))
            db.commit()
        client.post('/api/v1/auth/login',json={'login':'other','password':'AuditOther123!'})
        assert client.patch('/api/v1/tasks/t1',json={'status':'done'}).status_code==403
        assert client.get('/api/v1/audit').json()==[]
        data=client.get('/api/v1/dashboard').json()
        assert data['patients']==[]
        assert data['settings']['name']=='Other Doctor'


def test_max_codes_are_case_sensitive_and_expire_in_24_hours():
    from app.max_bot import create_link_code, hash_link_code
    from app.models import MaxLinkCode
    from sqlalchemy import select
    with TestClient(app),SessionLocal() as db:
        code=create_link_code(db,'p1','doctor-demo',1440)
        db.flush()
        row=db.scalar(select(MaxLinkCode).where(MaxLinkCode.code_hash==hash_link_code(code)))
        assert row is not None
        assert timedelta(hours=23,minutes=59)<row.expires_at-datetime.utcnow()<=timedelta(hours=24)
        assert hash_link_code(code)!=hash_link_code(code.lower())
