cd c:\
cd software
cd tripathi
git pull
copy /b/v/y db.sqlite3 backup.sqlite3
git add *
git commit -m "file"
git push
python manage.py runserver