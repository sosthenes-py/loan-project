from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("SHOW timezone;")
    result = cursor.fetchone()
    print(f"Database Timezone: {result[0]}")
