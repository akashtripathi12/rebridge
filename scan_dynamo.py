import boto3
import os
os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

dynamodb = boto3.resource('dynamodb', endpoint_url='http://dynamodb-local:8000')
table = dynamodb.Table('rebridge')
resp = table.scan()
for item in resp['Items']:
    if item['SK'] == 'META':
        print(item.get('item_id'), item.get('expected_price'))
