cd d:
d:
cd software\tripathi
git pull
copy db_vat_bill.sqlite3 backup_vat.sqlite3
git add backup_vat.sqlite3
git commit -m "adding backup"
git push
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:80 vatBill
