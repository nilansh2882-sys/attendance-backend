import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import joblib
import os

MODEL_FILE = 'attendance_predictor.pkl'
FEATURE_COLS = [
    'current_pct',        # Overall attendance percentage 
    'recent_7day_pct',    # Attendance pct in the last 7 recorded days
    'recent_14day_pct',   # Attendance pct in the last 14 recorded days
    'absent_streak',      # Current streak of consecutive absences
    'days_recorded',      # Total number of days recorded so far
    'days_remaining'      # Days left in the semester (approximate)
]

def generate_synthetic_training_data(num_samples=1000):
    """
    Generates synthetic data simulating past students' mid-semester attendance metrics
    and their final outcome (whether they met the 75% criteria at the end of the semester).
    """
    np.random.seed(42)
    
    # 100 total days in a typical semester, imagine prediction is made at random points between day 20 and day 80
    days_recorded = np.random.randint(20, 80, num_samples)
    days_remaining = 100 - days_recorded
    
    # Random overall attendance so far
    current_pct = np.random.normal(70, 15, num_samples)
    current_pct = np.clip(current_pct, 10, 100) # Keep between 10% and 100%
    
    # Recent trend (usually correlated with overall, but with some variation)
    recent_14day_pct = current_pct + np.random.normal(0, 10, num_samples)
    recent_14day_pct = np.clip(recent_14day_pct, 0, 100)
    
    recent_7day_pct = recent_14day_pct + np.random.normal(0, 5, num_samples)
    recent_7day_pct = np.clip(recent_7day_pct, 0, 100)
    
    # Absent streaks (more likely if recent pct is low)
    absent_streak = np.zeros(num_samples)
    for i in range(num_samples):
        if recent_7day_pct[i] < 30:
            absent_streak[i] = np.random.randint(3, 8)
        elif recent_7day_pct[i] < 60:
            absent_streak[i] = np.random.randint(0, 4)
        else:
            absent_streak[i] = np.random.randint(0, 2)
            
    # Calculate final outcome (Did they meet 75%?)
    # Formula assumes future attendance will roughly follow a weighted average of current and recent trends
    future_attendance_pct = (0.3 * current_pct) + (0.7 * recent_14day_pct) + np.random.normal(0, 8, num_samples)
    
    final_overall_pct = ((current_pct * days_recorded) + (future_attendance_pct * days_remaining)) / 100
    
    # Target variable: 1 if final >= 75%, else 0
    met_criteria = (final_overall_pct >= 75).astype(int)
    
    data = pd.DataFrame({
        'current_pct': current_pct,
        'recent_7day_pct': recent_7day_pct,
        'recent_14day_pct': recent_14day_pct,
        'absent_streak': absent_streak,
        'days_recorded': days_recorded,
        'days_remaining': days_remaining,
        'met_criteria': met_criteria
    })
    
    return data

def train_and_save_model():
    print("Generating synthetic data and training ML model...")
    df = generate_synthetic_training_data(2000)
    
    X = df[FEATURE_COLS]
    y = df['met_criteria']
    
    # Train the Random Forest
    clf = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=6)
    clf.fit(X, y)
    
    # Save Model
    joblib.dump(clf, MODEL_FILE)
    print(f"Model saved to {MODEL_FILE}")
    
def load_model():
    if not os.path.exists(MODEL_FILE):
        train_and_save_model()
    return joblib.load(MODEL_FILE)

def calculate_student_features(attendance_records, semester_total_days=100):
    """
    Given a list of a student's attendance records (sorted by date), 
    calculate the features needed for the ML model.
    Records format: [{'status': 'present'/'absent', 'date': '...'}, ...]
    """
    days_recorded = len(attendance_records)
    days_remaining = max(0, semester_total_days - days_recorded)
    
    if days_recorded == 0:
        return {
            'current_pct': 0, 'recent_7day_pct': 0, 'recent_14day_pct': 0, 
            'absent_streak': 0, 'days_recorded': 0, 'days_remaining': semester_total_days
        }
        
    # Overall pct
    present_total = sum(1 for r in attendance_records if r['status'] == 'present')
    current_pct = (present_total / days_recorded) * 100
    
    # Recent 14 days
    recent_14 = attendance_records[-14:]
    present_14 = sum(1 for r in recent_14 if r['status'] == 'present')
    recent_14day_pct = (present_14 / len(recent_14)) * 100 if recent_14 else 0
    
    # Recent 7 days
    recent_7 = attendance_records[-7:]
    present_7 = sum(1 for r in recent_7 if r['status'] == 'present')
    recent_7day_pct = (present_7 / len(recent_7)) * 100 if recent_7 else 0
    
    # Absent streak
    absent_streak = 0
    for r in reversed(attendance_records):
        if r['status'] == 'absent':
            absent_streak += 1
        else:
            break
            
    return {
        'current_pct': current_pct,
        'recent_7day_pct': recent_7day_pct,
        'recent_14day_pct': recent_14day_pct,
        'absent_streak': absent_streak,
        'days_recorded': days_recorded,
        'days_remaining': days_remaining
    }

def predict_student_outcome(attendance_records):
    """
    Predicts if a student will reach the 75% attendance criteria.
    Returns: dict with prediction, probability, risk_level, and recommended_actions.
    """
    model = load_model()
    features_dict = calculate_student_features(attendance_records)
    
    # If no records, model can't predict accurately. Give a neutral response.
    if features_dict['days_recorded'] == 0:
        return {
            'will_meet_criteria': True,
            'probability': 100,
            'risk_level': 'Safe',
            'current_attendance': 0,
            'recommendation': 'No attendance records yet. Start attending classes!'
        }
    
    # Format for model input
    X_input = pd.DataFrame([features_dict])
    
    # Predict
    prob = model.predict_proba(X_input)[0][1] # Probability of class 1 (meeting criteria)
    prob_pct = round(prob * 100)
    
    will_meet = prob >= 0.5
    
    # Determine risk level & recommendation
    current_pct = features_dict['current_pct']
    
    if prob_pct >= 80:
        risk_level = 'Safe'
        rec = "You're on track! Keep up the good attendance."
    elif prob_pct >= 50:
        risk_level = 'Warning'
        rec = "You have a fair chance, but your margin of error is small. Don't skip upcoming classes."
    else:
        risk_level = 'Critical'
        if features_dict['absent_streak'] >= 3:
            rec = f"You are falling behind! You have missed {features_dict['absent_streak']} consecutive classes. Urgent improvement needed."
        else:
            rec = "You are mathematically at high risk of falling below 75%. Perfect attendance is required from now on."
            
    return {
        'will_meet_criteria': bool(will_meet),
        'probability': prob_pct,
        'risk_level': risk_level,
        'current_attendance': round(current_pct),
        'features_used': features_dict,
        'recommendation': rec
    }

if __name__ == '__main__':
    train_and_save_model()
