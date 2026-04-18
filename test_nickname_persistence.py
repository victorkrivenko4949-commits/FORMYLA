"""
Тест для проверки сохранения никнейма в базе данных
"""
import sys
import os

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import User

def test_nickname_persistence():
    """Проверка, что никнейм сохраняется в БД и восстанавливается после перезагрузки"""
    
    with app.app_context():
        # Создаем тестового пользователя
        test_email = "test_nickname@example.com"
        
        # Удаляем если существует
        existing = User.query.filter_by(email=test_email).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
        
        # Создаем нового пользователя
        user = User(email=test_email, name="Test User")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        
        print(f"✓ Создан пользователь ID={user_id}, email={test_email}")
        
        # Устанавливаем никнейм
        test_nickname = "test_user_123"
        user.nickname = test_nickname
        db.session.commit()
        db.session.refresh(user)  # Обновляем объект из БД
        
        print(f"✓ Установлен никнейм: {user.nickname}")
        
        # Проверяем, что никнейм сохранен в памяти
        assert user.nickname == test_nickname, f"Никнейм в памяти не совпадает: {user.nickname} != {test_nickname}"
        print(f"✓ Никнейм в памяти корректен: {user.nickname}")
        
        # Симулируем "перезагрузку" - загружаем пользователя заново из БД
        db.session.expire_all()  # Очищаем кэш сессии
        user_reloaded = User.query.get(user_id)
        
        print(f"✓ Пользователь перезагружен из БД")
        print(f"  - ID: {user_reloaded.id}")
        print(f"  - Email: {user_reloaded.email}")
        print(f"  - Nickname: {user_reloaded.nickname}")
        
        # Проверяем, что никнейм сохранился в БД
        assert user_reloaded.nickname == test_nickname, f"Никнейм не сохранился в БД: {user_reloaded.nickname} != {test_nickname}"
        print(f"✓ Никнейм восстановлен из БД: {user_reloaded.nickname}")
        
        # Очистка
        db.session.delete(user_reloaded)
        db.session.commit()
        print(f"✓ Тестовый пользователь удален")
        
        print("\n" + "="*60)
        print("✅ ТЕСТ ПРОЙДЕН! Никнейм корректно сохраняется в БД и восстанавливается после перезагрузки.")
        print("="*60)

if __name__ == "__main__":
    try:
        test_nickname_persistence()
    except AssertionError as e:
        print(f"\n❌ ТЕСТ ПРОВАЛЕН: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
