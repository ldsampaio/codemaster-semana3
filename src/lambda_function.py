import json
import boto3
from decimal import Decimal
import logging
import os

# Incluindo um comentário para testar o workflow do Github Actions

TABLE_NAME = os.environ.get('TABLE_NAME', 'usuarios')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Cliente DynamoDB
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)

# Helper para serializar Decimal
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)

def lambda_handler(event, context):
    logger.info(f"Event: {json.dumps(event)}")

    http_method = event.get('httpMethod', 'GET')
    path_parameters = event.get('pathParameters') or {}
    query_parameters = event.get('queryStringParameters') or {}
    body = event.get('body', '{}')

    # Parse body se for string JSON
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            body = {}

    try:
        if http_method == 'GET' and 'user_id' in path_parameters:
            # READ ONE: GET /users/{user_id}
            return get_user(path_parameters['user_id'])

        elif http_method == 'GET':
            # READ ALL: GET /users (com paginação opcional)
            return get_users(query_parameters)

        elif http_method == 'POST':
            # CREATE: POST /users
            return create_user(body)

        elif http_method == 'PUT' and 'user_id' in path_parameters:
            # UPDATE: PUT /users/{user_id}
            return update_user(path_parameters['user_id'], body)

        elif http_method == 'DELETE' and 'user_id' in path_parameters:
            # DELETE: DELETE /users/{user_id}
            return delete_user(path_parameters['user_id'])

        else:
            return response(400, {'error': 'Método ou path inválido'})

    except Exception as e:
        logger.error(f"Erro: {str(e)}")
        return response(500, {'error': str(e)})

def get_user(user_id):
    """Busca usuário por ID."""
    result = table.get_item(Key={'user_id': user_id})
    item = result.get('Item')

    if not item:
        return response(404, {'error': 'Usuário não encontrado'})

    return response(200, {'user': item})

def get_users(query_params):
    """Lista usuários com paginação (scan simplificado)."""
    limit = int(query_params.get('limit', 10))

    # NOTA: Em produção, use Query com índice, não Scan
    result = table.scan(Limit=limit)

    return response(200, {
        'users': result['Items'],
        'count': result['Count'],
        'last_key': result.get('LastEvaluatedKey')
    })

def create_user(data):
    """Cria novo usuário."""
    if 'user_id' not in data:
        return response(400, {'error': 'user_id obrigatório'})

    # Verificar se já existe
    existing = table.get_item(Key={'user_id': data['user_id']})
    if existing.get('Item'):
        return response(409, {'error': 'Usuário já existe'})

    # Garantir que valores numéricos sejam Decimal
    if 'idade' in data and isinstance(data['idade'], (int, float)):
        data['idade'] = Decimal(str(data['idade']))

    table.put_item(Item=data)
    return response(201, {'message': 'Usuário criado', 'user': data})

def update_user(user_id, data):
    """Atualiza usuário existente."""
    # Verificar existência
    existing = table.get_item(Key={'user_id': user_id})
    if not existing.get('Item'):
        return response(404, {'error': 'Usuário não encontrado'})

    # Construir UpdateExpression dinâmica
    update_parts = []
    expression_values = {}

    for key, value in data.items():
        if key != 'user_id':  # não atualizar chave primária
            update_parts.append(f"{key} = :{key}")
            if isinstance(value, (int, float)):
                value = Decimal(str(value))
            expression_values[f':{key}'] = value

    if not update_parts:
        return response(400, {'error': 'Nenhum campo para atualizar'})

    update_expression = "SET " + ", ".join(update_parts)

    result = table.update_item(
        Key={'user_id': user_id},
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_values,
        ReturnValues='ALL_NEW'
    )

    return response(200, {'message': 'Usuário atualizado', 'user': result['Attributes']})

def delete_user(user_id):
    """Deleta usuário."""
    # Verificar existência antes de deletar
    existing = table.get_item(Key={'user_id': user_id})
    if not existing.get('Item'):
        return response(404, {'error': 'Usuário não encontrado'})

    table.delete_item(Key={'user_id': user_id})
    return response(200, {'message': 'Usuário deletado'})

def response(status_code, body):
    """Helper para respostas HTTP padronizadas."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body, cls=DecimalEncoder)
    }