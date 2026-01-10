# ingestion_db.py
import os
import time
import logging
import pandas as pd
from sqlalchemy import create_engine

# Configure logging
logging.basicConfig(
    filename='logs/ingestion_db.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='a'
)

def ingest_db(df: pd.DataFrame, table_name: str, engine) -> None:
    """
    Ingest a Pandas DataFrame into a database table.

    Parameters:
        df (pd.DataFrame): Data to insert.
        table_name (str): Name of the database table.
        engine (SQLAlchemy Engine): Database connection engine.
    """
    df.to_sql(table_name, con=engine, if_exists='replace', index=False)
    logging.info(f"Table '{table_name}' successfully ingested with {len(df)} rows.")

def load_raw_data(data_dir: str, engine) -> None:
    """
    Load all CSV files from the specified directory into the database.

    Parameters:
        data_dir (str): Path to the folder containing CSV files.
        engine (SQLAlchemy Engine): Database connection engine.
    """
    start_time = time.time()

    for file in os.listdir(data_dir):
        if file.lower().endswith('.csv'):
            file_path = os.path.join(data_dir, file)
            try:
                df = pd.read_csv(file_path)
                logging.info(f"Ingesting '{file}' into the database...")
                ingest_db(df, file[:-4], engine)
            except Exception as e:
                logging.error(f"Failed to load '{file}': {e}", exc_info=True)

    elapsed_time = time.time() - start_time
    logging.info("------- Ingestion Complete -----------")
    logging.info(f"Total Time Taken: {elapsed_time:.2f} seconds")

if __name__ == '__main__':
    engine = create_engine('sqlite:///inventory.db')
    load_raw_data('data', engine)
