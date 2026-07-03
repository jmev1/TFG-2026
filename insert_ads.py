# db_loader.py - El definitivo
import json
import re
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path
import time

CONFIG_FILE = "config/db_config.json"

class CochesDBLoader:
    def __init__(self, dbname="anuncios", user="postgres", password=None):
        self.conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host="localhost",
            port="5432"
        )
        self.create_tables()


    #Crea tablas e índices
    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS anuncios (
                id VARCHAR PRIMARY KEY,
                brand VARCHAR(50),
                model VARCHAR(200),
                price INTEGER,
                original_price INTEGER,
                year INTEGER,
                km INTEGER,
                cv INTEGER,
                cc INTEGER,
                fuel VARCHAR(50),
                transmission VARCHAR(50),
                doors INTEGER,
                seats INTEGER,
                car_type VARCHAR(50),
                location VARCHAR(100),
                label VARCHAR(100),
                comments TEXT,
                url VARCHAR(500),
                extendido VARCHAR(20),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_brand ON anuncios(brand);
            CREATE INDEX IF NOT EXISTS idx_price ON anuncios(price);
            CREATE INDEX IF NOT EXISTS idx_year ON anuncios(year);
            CREATE INDEX IF NOT EXISTS idx_brand_year ON anuncios(brand, year);
        """)
        self.conn.commit()

    #Carga todos los JSONs en batches
    def load_from_json_dir(self, data_dir="data/", batch_size=1000):
        data_path = Path(data_dir)
        files = list(data_path.glob("*.json"))
        total = len(files)
        
        print(f"Encontrados {total} archivos JSON")
        
        batch = []
        loaded = 0
        start_time = time.time()
        
        for i, file in enumerate(files, 1):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    ad = json.load(f)
                    
                    if ad.get('extendido') == 'S':
                        # completo las ubiaciones e los anuncios mal extendidas
                        if ad.get('location') is None:
                            location =  re.search(r"-en-([a-zA-Z\-]+)-\d+", ad.get('url'))
                            if location:
                                location = location.group(1)
                            else:
                                location = None
                            ad['location'] = location
                        batch.append(ad)
                        
                        if len(batch) >= batch_size:
                            self._insert_batch(batch)
                            loaded += len(batch)
                            batch = []
                            print(f"{loaded}/{total} ({loaded/total*100:.1f}%)")
            
            except Exception as e:
                print(f"Error en {file}: {e}")
        
        # Insertar último batch
        if batch:
            self._insert_batch(batch)
            loaded += len(batch)
        
        elapsed = time.time() - start_time
        print(f"\n{loaded} anuncios cargados en {elapsed:.2f}s ({loaded/elapsed:.0f} ads/s)")
        self.print_stats()

    #Inserta batch con UPSERT
    def _insert_batch(self, ads):
        
        cursor = self.conn.cursor()
        
        values = [
            (
                ad.get('id'), ad.get('brand'), ad.get('model'),
                ad.get('price'), ad.get('original_price'), ad.get('year'),
                ad.get('km'), ad.get('cv'), ad.get('cc'),
                ad.get('fuel'), ad.get('transmission'), ad.get('doors'),
                ad.get('seats'), ad.get('type'), ad.get('location'),
                ad.get('label'), ad.get('comments'), ad.get('url'),
                ad.get('extendido')
            )
            for ad in ads
        ]
        
        execute_values(
            cursor,
            """
            INSERT INTO anuncios (id, brand, model, price, original_price, year, km, cv, cc,
                             fuel, transmission, doors, seats, car_type, location, label,
                             comments, url, extendido)
            VALUES %s
            ON CONFLICT (id) DO UPDATE SET
                price = EXCLUDED.price,
                km = EXCLUDED.km,
                updated_at = NOW()
            """,
            values
        )
        
        self.conn.commit()
    
    #Imprime estadísticas de la DB
    def print_stats(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                AVG(price)::INTEGER as avg_price,
                COUNT(DISTINCT brand) as brands
            FROM anuncios
        """)
        
        total, avg_price, brands = cursor.fetchone()
        print(f"\nEstadísticas:")
        print(f"Total anuncios: {total:,}")
        print(f"Precio medio: {avg_price:,}€")
        print(f"Marcas únicas: {brands}")
    
    def close(self):
        self.conn.close()

# Usar
if __name__ == "__main__":
    
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)

    #print(config)

    loader = CochesDBLoader(password=config["password"])
    loader.load_from_json_dir("data/")
    loader.close()