from datetime import datetime, timedelta


def _parse_ts(ts_str):
    try:
        return datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
    except Exception:
        return datetime.min


def build_trajectories(events):
    """
    Будує траєкторії з послідовних подій.
    Групує події з однаковим типом (drone/missile/flyover) що йдуть одна за одною
    в межах 3 годин і мають різні міста.
    """
    trajectories = []

    # Фільтруємо тільки події з координатами
    geo_events = [e for e in events if e.get('lat') and e.get('lon')]

    # Групуємо по типу
    for event_type in ['drone', 'missile', 'flyover']:
        type_events = [e for e in geo_events if e['event_type'] == event_type]
        if len(type_events) < 2:
            continue

        # Сортуємо по часу
        type_events.sort(key=lambda x: x['timestamp'])

        # Шукаємо послідовності
        used = set()
        for i, e1 in enumerate(type_events):
            if i in used:
                continue
            chain = [e1]
            used.add(i)

            for j, e2 in enumerate(type_events[i + 1:], i + 1):
                if j in used:
                    continue

                last = chain[-1]
                t_last = _parse_ts(last['timestamp'])
                t2 = _parse_ts(e2['timestamp'])

                # В межах 3 годин і різне місто
                if (t2 > t_last and
                        (t2 - t_last) <= timedelta(hours=3) and
                        e2['city'] != last['city'] and
                        e2['city'] is not None):
                    chain.append(e2)
                    used.add(j)
                    if len(chain) >= 6:  # Максимум 6 точок в траєкторії
                        break

            if len(chain) >= 2:
                trajectories.append({
                    'type': event_type,
                    'points': [[e['lat'], e['lon']] for e in chain],
                    'cities': [e['city'] for e in chain],
                    'events': chain,
                })

    return trajectories
