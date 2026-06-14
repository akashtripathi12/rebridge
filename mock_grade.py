import requests
import boto3
from rebridge_data.dynamo_item_repository import DynamoItemRepository
from rebridge_data.models import GradeRecord

item_id = '567334d8feab40e0b35d2083a079c213'
repo = DynamoItemRepository(boto3.resource('dynamodb', endpoint_url='http://localhost:8000', region_name='us-east-1').Table('ReBridge-Items-Local'))

repo.put_grade(item_id, GradeRecord(
    grade='Very Good',
    confidence=0.9,
    summary='mock',
    defects=[],
    confirmed=False
))
print('Graded')
