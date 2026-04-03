from datetime import datetime, timedelta

def test_filtering():
    live_data = [
        # Tuesday Created, Wed Event (Last week)
        {'id': '1', 'created_at': '2026-02-17T13:50:06.970747+00:00', 'course_code': 'MT2005', 'original_day': 'Wed'},
        # Wed Created, Today Event
        {'id': '2', 'created_at': '2026-02-25T13:50:06.970+00:00', 'course_code': 'TODAY_CS', 'original_day': 'Thu'},
        # Today Created, Tomorrow Event
        {'id': '3', 'created_at': '2026-02-26T13:50:06.970+00:00', 'course_code': 'TOMORROW_MA', 'original_day': 'Fri'},
    ]
    
    # Let pkt_now be Thursday, Feb 26 2026 03:00 AM (which is Vercel Wed Feb 25 10:00 PM)
    pkt_now = datetime(2026, 2, 26, 3, 0)
    
    day_map = {'Mon':0, 'Tue':1, 'Wed':2, 'Thu':3, 'Fri':4, 'Sat':5, 'Sun':6}
                
    filtered_live_data = []
    for l in live_data:
        update_day = l.get('original_day', 'Mon')[:3]
        if update_day != 'N/A' and update_day in day_map:
            try:
                dt_str = l['created_at'][:19]
                created_dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")
                created_dt_pkt = created_dt + timedelta(hours=5)
                
                update_day_idx = day_map[update_day]
                created_day_idx = created_dt_pkt.weekday()
                
                # If the day is exactly the same, days_diff is 0, so event_date = created_dt_pkt.date().
                # If event_date < pkt_now.date(), it happened earlier today? 
                # No, if event_date == pkt_now.date(), event_date < pkt_now.date() is False (it stays).
                # If event_date was yesterday, it goes True.
                days_diff = update_day_idx - created_day_idx
                if days_diff < 0:
                    days_diff += 7  # It's next week
                    
                event_date = created_dt_pkt.date() + timedelta(days=days_diff)
                print(f"Update: {l['course_code']}, Created: {created_dt_pkt.date()}, Event Day: {update_day}, Calculated Date: {event_date}, Now: {pkt_now.date()}")
                
                if event_date < pkt_now.date():
                    print("  -> SKIPPING (Past)")
                    continue
            except Exception as e:
                print(f"Error parsing date obj: {e}")
        
        filtered_live_data.append(l)

test_filtering()
