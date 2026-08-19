from app.database import SessionLocal
from app.models.models import RoleAccess

db = SessionLocal()

roles = [

    # =========================
    # PLANT 2
    # =========================

    RoleAccess(
        plant_id=2,
        role="production",
        person_name="Rammohan Tummala",
        email="tummala.rammohan@ranegroup.com"
    ),

    RoleAccess(
        plant_id=2,
        role="sales",
        person_name="M.S.Sukesh",
        email="ms.sukesh@ranegroup.com"
    ),

    RoleAccess(
        plant_id=2,
        role="manpower",
        person_name="Balakrishnaiah D",
        email="d.balakrishnaiah@ranegroup.com"
    ),

    RoleAccess(
        plant_id=2,
        role="ovc",
        person_name="Venkata Narayana C",
        email="c.venkatanarayana@ranegroup.com"
    ),

    RoleAccess(
        plant_id=2,
        role="product_value",
        person_name="Venkata Narayana C",
        email="c.venkatanarayana@ranegroup.com"
    ),

    RoleAccess(
        plant_id=2,
        role="despatch",
        person_name="Prasanna Kumar P",
        email="p.prasannakumar@ranegroup.com"
    ),

    RoleAccess(
        plant_id=2,
        role="rejection_ppm",
        person_name="Mahesh Batta",
        email="mahesh.batta@ranegroup.com"
    ),

    # =========================
    # PLANT 3
    # =========================

    RoleAccess(
        plant_id=3,
        role="production",
        person_name="O Pannerselvam",
        email="vb.lokesh@ranegroup.com"
    ),

    RoleAccess(
        plant_id=3,
        role="sales",
        person_name="M.S.Sukesh",
        email="ms.sukesh@ranegroup.com"
    ),

    RoleAccess(
        plant_id=3,
        role="manpower",
        person_name="R.Senthil",
        email=" "
    ),

    RoleAccess(
        plant_id=3,
        role="ovc",
        person_name="Thamaraj S",
        email="s.thamaraj@ranegroup.com"
    ),

    RoleAccess(
        plant_id=3,
        role="product_value",
        person_name="Thamaraj S",
        email="s.thamaraj@ranegroup.com"
    ),

    RoleAccess(
        plant_id=3,
        role="despatch",
        person_name="Manibharathi U",
        email="u.manibharathi@ranegroup.com"
    ),

    RoleAccess(
        plant_id=3,
        role="rejection_ppm",
        person_name="Praveen S",
        email=""
    ),

    # =========================
    # PLANT 4
    # =========================

    RoleAccess(
        plant_id=4,
        role="production",
        person_name="CH CH V Ramana",
        email="k.chchvramana@ranegroup.com"
    ),

    RoleAccess(
        plant_id=4,
        role="sales",
        person_name="M.S.Sukesh",
        email="ms.sukesh@ranegroup.com"
    ),

    RoleAccess(
        plant_id=4,
        role="manpower",
        person_name="Gopinath Karrotu",
        email="a.gopinadhkarrotu@ranegroup.com"
    ),

    RoleAccess(
        plant_id=4,
        role="ovc",
        person_name="Malla Naresh",
        email="malla.naresh@ranegroup.com"
    ),

    RoleAccess(
        plant_id=4,
        role="product_value",
        person_name="Malla Naresh",
        email="malla.naresh@ranegroup.com"
    ),

    RoleAccess(
        plant_id=4,
        role="despatch",
        person_name="Satheesh Babu Geedala",
        email="geedala.satheeshbabu@ranegroup.com"
    ),

    RoleAccess(
        plant_id=4,
        role="rejection_ppm",
        person_name="G.Nagaraju",
        email="g.nagaraju@ranegroup.com"
    ),

    # =========================
    # PLANT 5
    # =========================

    RoleAccess(
        plant_id=5,
        role="production",
        person_name="C.Satheeshkumar",
        email="c.satheeshkumar@ranegroup.com"
    ),

    RoleAccess(
        plant_id=5,
        role="sales",
        person_name="M.S.Sukesh",
        email="ms.sukesh@ranegroup.com"
    ),

    RoleAccess(
        plant_id=5,
        role="manpower",
        person_name="K.Lawrence",
        email="k.lawrence@ranegroup.com"
    ),

    RoleAccess(
        plant_id=5,
        role="ovc",
        person_name="Mahalaxmy K",
        email="k.mahalaxmy@ranegroup.com"
    ),

    RoleAccess(
        plant_id=5,
        role="product_value",
        person_name="Mahalaxmy K",
        email="k.mahalaxmy@ranegroup.com"
    ),

    RoleAccess(
        plant_id=5,
        role="despatch",
        person_name="Gopalakrishnan S",
        email="ps.gopalakrishnan@ranegroup.com"
    ),

    RoleAccess(
        plant_id=5,
        role="rejection_ppm",
        person_name="A.Manikandan",
        email="ca.manikandan@ranegroup.com"
    ),

    # =========================
    # PLANT 6
    # =========================

    RoleAccess(
        plant_id=6,
        role="production",
        person_name="A.Arulsundaram",
        email="sa.arulsundaram@ranegroup.com"
    ),

    RoleAccess(
        plant_id=6,
        role="sales",
        person_name="M.S.Sukesh",
        email="ms.sukesh@ranegroup.com"
    ),

    RoleAccess(
        plant_id=6,
        role="manpower",
        person_name="Kalkoti Channabasappa",
        email="kalkoti.channabasappa@ranegroup.com"
    ),

    RoleAccess(
        plant_id=6,
        role="ovc",
        person_name="Vijayakumar R",
        email="r.vijayakumar@ranegroup.com"
    ),

    RoleAccess(
        plant_id=6,
        role="product_value",
        person_name="Vijayakumar R",
        email="r.vijayakumar@ranegroup.com"
    ),

    RoleAccess(
        plant_id=6,
        role="despatch",
        person_name="Nagesh AB",
        email="ab.nagesh@ranegroup.com"
    ),

    RoleAccess(
        plant_id=6,
        role="rejection_ppm",
        person_name="Sathishkumar T",
        email=""
    ),
]

for role in roles:
    db.add(role)

db.commit()
db.close()

print("✅ Role Access data inserted successfully!")