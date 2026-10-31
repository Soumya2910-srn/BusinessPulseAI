import os
import math
import pandas as pd

# Pure Python Linear Regression implementation (gradient descent / normal equation)
class SimpleLinearRegression:
    def __init__(self):
        self.slope = 0.0
        self.intercept = 0.0

    def fit(self, X, y):
        n = len(X)
        if n == 0:
            return
        mean_x = sum(X) / n
        mean_y = sum(y) / n
        
        numerator = sum((X[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        denominator = sum((X[i] - mean_x) ** 2 for i in range(n))
        
        if denominator != 0:
            self.slope = numerator / denominator
            self.intercept = mean_y - (self.slope * mean_x)
        else:
            self.slope = 0.0
            self.intercept = mean_y

    def predict(self, x_val):
        return self.slope * x_val + self.intercept

def clean_and_process_dataframe(df):
    """
    Cleans a pandas DataFrame by removing duplicates, fixing dates, 
    and imputing missing values.
    """
    # 1. Duplicate Removal
    df.drop_duplicates(inplace=True)

    # 2. Date Formatting
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        # Fill missing dates using forward fill
        df['Date'] = df['Date'].ffill()
    
    # 3. Numeric Types and Missing Value Handling
    numeric_cols = ['Units_Sold', 'Unit_Price', 'Revenue', 'Marketing_Spend', 'New_Customers']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            # Impute missing numeric values with the median
            median_val = df[col].median()
            if pd.isna(median_val):
                median_val = 0.0
            df[col] = df[col].fillna(median_val)

    # 4. Categorical handling
    if 'Product_Category' in df.columns:
        df['Product_Category'] = df['Product_Category'].fillna('Unknown_Category')
        
    return df

def load_dataset(filepath):
    if not os.path.exists(filepath):
        return []
    
    try:
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return []

    df = clean_and_process_dataframe(df)
    
    data = []
    for _, row in df.iterrows():
        try:
            data.append({
                'Units_Sold': float(row.get('Units_Sold', 0)),
                'Unit_Price': float(row.get('Unit_Price', 0)),
                'Revenue': float(row.get('Revenue', 0)),
                'Marketing_Spend': float(row.get('Marketing_Spend', 0)),
                'New_Customers': float(row.get('New_Customers', 0)),
                'Category': str(row.get('Product_Category', 'Unknown')).strip()
            })
        except Exception:
            continue

    return data

def train_model():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    prev_path = os.path.join(base_dir, "previous_month_dataset.csv")
    curr_path = os.path.join(base_dir, "current_month_dataset.csv")

    prev_data = load_dataset(prev_path)
    curr_data = load_dataset(curr_path)

    combined_data = prev_data + curr_data

    if not combined_data:
        print("Error: No valid dataset records found for training.")
        return

    print("==================================================")
    print("      MACHINE LEARNING MODEL TRAINING SCRIPT      ")
    print("==================================================")
    print(f"Total training samples loaded: {len(combined_data)}")

    # Model 1: Predict Revenue based on Marketing Spend (Linear Regression)
    X_mkt = [d['Marketing_Spend'] for d in combined_data]
    y_rev = [d['Revenue'] for d in combined_data]

    model_rev = SimpleLinearRegression()
    model_rev.fit(X_mkt, y_rev)

    print("\n--- Model 1: Marketing Spend vs Revenue (Linear Regression) ---")
    print(f"Learned Equation: Revenue = ({model_rev.slope:.2f} * Marketing_Spend) + {model_rev.intercept:.2f}")

    # Model 2: Predict New Customers based on Units Sold (Linear Regression)
    X_units = [d['Units_Sold'] for d in combined_data]
    y_cust = [d['New_Customers'] for d in combined_data]

    model_cust = SimpleLinearRegression()
    model_cust.fit(X_units, y_cust)

    print("\n--- Model 2: Units Sold vs New Customers (Linear Regression) ---")
    print(f"Learned Equation: New_Customers = ({model_cust.slope:.4f} * Units_Sold) + {model_cust.intercept:.2f}")

    # Forecasting next month metrics
    sample_mkt_budget = 2000.0
    predicted_revenue = model_rev.predict(sample_mkt_budget)
    print(f"\n[PREDICTION SAMPLE] If Marketing Spend = ${sample_mkt_budget:.2f} -> Forecasted Revenue = ${predicted_revenue:.2f}")

    return {
        'model_rev': model_rev,
        'model_cust': model_cust
    }

if __name__ == "__main__":
    train_model()
