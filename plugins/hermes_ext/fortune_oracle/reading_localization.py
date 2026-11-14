"""Translate presentation of completed P1 readings without recalculation or draws.

English prompts are authored equivalents of our Korean reflection prompts;
not classical text translations. Numeric IDs and underlying evidence stay intact.
"""
from copy import deepcopy
from .localization import language_code, ELEMENT_EN, DISCLAIMER_EN, _STEMS

MAJOR_EN = (
 ('The Fool','Start small and learn from experience','rushing in without preparation'),
 ('The Magician','Use the skills and resources you already have','planning without taking action'),
 ('The High Priestess','Observe quietly and listen to your own criteria','treating an unchecked guess as fact'),
 ('The Empress','Care for yourself and support growth around you','carrying all the care work alone'),
 ('The Emperor','Clarify roles and boundaries','trying to control too much'),
 ('The Hierophant','Review the principles and advice you have learned','following convention without questioning it'),
 ('The Lovers','Align your choices with important values','postponing choices to meet others expectations'),
 ('The Chariot','Focus effort on one goal','missing signals while accelerating'),
 ('Strength','Handle the situation with calm and patience','suppressing feelings or forcing an outcome'),
 ('The Hermit','Make time to reflect and find your own criteria','isolating yourself when help is needed'),
 ('Wheel of Fortune','Adjust your plans as circumstances change','taking responsibility for everything outside your control'),
 ('Justice','Review evidence and responsibilities fairly','selecting only information that favors you'),
 ('The Hanged Man','Pause and consider another perspective','accepting sacrifice as an automatic obligation'),
 ('Death','Finish an outdated role and make room for something new','holding on to a way that has run its course'),
 ('Temperance','Balance different needs','pushing on without recovery'),
 ('The Devil','Notice dependencies and regain choices','repeating a dependency to avoid discomfort'),
 ('The Tower','Review a shaken assumption and rebuild it','ignoring warning signs to avoid change'),
 ('The Star','Keep a small, practical source of hope','substituting hope for action'),
 ('The Moon','Distinguish uncertain information from feelings','treating anxiety as fact'),
 ('The Sun','Share clear goals and progress','seeing only the bright side and missing problems'),
 ('Judgement','Review experience and choose your next step','defining yourself by past mistakes'),
 ('The World','Connect and acknowledge completed experience','waiting for a perfect ending instead of finishing'),
)
_SUITS = (('Wands','motivation and action'),('Cups','feelings and relationships'),
          ('Swords','thought and communication'),('Pentacles','daily life and resources'))
_RANKS = (
 ('Ace','Choose one new attempt','postponing a beginning'),
 ('Two','Examine the difference between two options','avoiding a decision'),
 ('Three','Collaborate and seek feedback','guessing others opinions alone'),
 ('Four','Stabilize your foundation and rest','getting stuck in familiarity'),
 ('Five','Acknowledge conflict and what is lacking','exhausting yourself through comparison'),
 ('Six','Give and receive support to recover','staying only in the giving or receiving role'),
 ('Seven','Maintain and review your criteria','defending without checking'),
 ('Eight','Adjust through practice and focus','trying to solve everything with speed'),
 ('Nine','Review accumulated experience and limits','believing you must endure alone'),
 ('Ten','Share the burden of completion and the next stage','taking all responsibility yourself'),
 ('Page','Learn and ask questions','hiding what you do not yet know'),
 ('Knight','Choose a direction and move','pushing forward too hastily'),
 ('Queen','Care attentively and coordinate','putting your own needs last'),
 ('King','Use experience responsibly','insisting only your way is right'),
)
TAROT_EN = MAJOR_EN + tuple((f'{rank} of {suit}',f'{area}: {focus}',f'{area}: {tension}')
    for suit,area in _SUITS for rank,focus,tension in _RANKS)
HEXAGRAM_EN = (
 ('The Creative','Take initiative while using your energy steadily'),
 ('The Receptive','Build a foundation for acceptance and cooperation'),
 ('Difficulty at the Beginning','Find a small sequence within the confusion of starting'),
 ('Youthful Inexperience','Acknowledge what you do not know and learn'),
 ('Waiting','Prepare while allowing time'),
 ('Conflict','Separate claims and evidence before escalating a dispute'),
 ('The Army','Clarify shared goals and responsibilities'),
 ('Holding Together','Consider whom to join and on what principles'),
 ('Small Accumulation','Gather gradually and delay a rushed expansion'),
 ('Treading','Respect others boundaries and procedures'),
 ('Peace','Maintain open communication and balance'),
 ('Standstill','Choose the principles to keep when progress is blocked'),
 ('Fellowship','Find a common purpose for cooperation'),
 ('Great Possession','Share available resources responsibly'),
 ('Modesty','Leave room to learn rather than displaying achievements'),
 ('Enthusiasm','Turn preparation and motivation into specific action'),
 ('Following','Adapt to circumstances without losing your criteria'),
 ('Work on What Has Been Spoiled','Review the causes of accumulated problems'),
 ('Approach','Move closer while respecting the other persons pace'),
 ('Contemplation','Observe before judging'),
 ('Biting Through','Address an obstacle through clear procedures'),
 ('Grace','Examine both presentation and substance'),
 ('Splitting Apart','Avoid further exhausting a weakened foundation'),
 ('Return','Return to basics and begin a small recovery'),
 ('Innocence','Choose verifiable actions rather than forced expectations'),
 ('Great Accumulation','Learn to refine the strength you have gathered'),
 ('Nourishment','Review what you take in and put out'),
 ('Great Excess','Reduce excessive burdens and share roles'),
 ('The Abysmal','Find a safe sequence within recurring difficulties'),
 ('The Clinging','Keep clear criteria and necessary connections'),
 ('Influence','Listen carefully to your effect on others'),
 ('Duration','Maintain sustainable habits'),
 ('Retreat','Step back from unnecessary competition'),
 ('Great Power','Add restraint and responsibility when you have strength'),
 ('Progress','Recognize progress and widen cooperation'),
 ('Darkening of the Light','Protect your principles in difficult circumstances'),
 ('The Family','Clarify roles and agreements in close relationships'),
 ('Opposition','Accept different perspectives and find common ground'),
 ('Obstruction','Seek help and another route when the path is blocked'),
 ('Deliverance','Release tension and address what remains'),
 ('Decrease','Choose what to reduce so you can preserve what matters'),
 ('Increase','Develop useful resources together'),
 ('Breakthrough','Clarify a decision while avoiding aggression'),
 ('Coming to Meet','Welcome a new encounter while reviewing boundaries'),
 ('Gathering Together','Align the purposes and roles of those gathered'),
 ('Pushing Upward','Build small steps of progress consistently'),
 ('Oppression','Conserve your remaining strength within constraints'),
 ('The Well','Care for a foundation everyone needs'),
 ('Revolution','Check the reasons and agreement for a change'),
 ('The Cauldron','Reorganize resources for a new approach'),
 ('The Arousing','Regain your center and sequence after a shock'),
 ('Keeping Still','Notice where to stop and rest'),
 ('Gradual Progress','Review stages and stability rather than speed'),
 ('The Marrying Maiden','Coordinate expectations and the sequence of a relationship'),
 ('Abundance','Check for overload even in a time of plenty'),
 ('The Wanderer','Move in small, flexible steps in unfamiliar surroundings'),
 ('The Gentle','Communicate gently and consistently'),
 ('The Joyous','Share enjoyment and honest communication'),
 ('Dispersion','Gather scattered attention around a common purpose'),
 ('Limitation','Set limits and rules you can maintain'),
 ('Inner Truth','Build trust through consistency between words and actions'),
 ('Small Excess','Focus on small adjustments rather than a large leap'),
 ('After Completion','Continue maintenance and review after finishing'),
 ('Before Completion','Acknowledge unfinished work and choose the next step'),
)


def localize_reading(reading, language='ko'):
    """Only format successful computed data or safe errors; never invoke a backend."""
    code = language_code(language)
    result = deepcopy(reading)
    result['language'] = code
    if code == 'ko':
        return result
    if not result.get('ok'):
        error = result.get('error')
        text = {'invalid_input':'Check your input. Tarot: question | 0 8r 21. I Ching: question | 7 8 7 8 7 8 (bottom first). Compatibility: YYYY-MM-DD [HH:MM] [IANA_ZONE] | YYYY-MM-DD [HH:MM] [IANA_ZONE].',
                'draw_unavailable':'The draw could not be completed. Please try again.',
                'calculation_unavailable':'Both birth profiles are required and must calculate successfully.',
                'unsupported_command':'Use a daily, Tarot, I Ching or compatibility command.'}.get(error,'The reading could not be completed. Please check your input.')
        if 'text_fallback' in result:
            result['text_fallback'] = text
        else:
            result['text'] = text
        return result
    if result.get('kind') == 'tarot':
        text = ['Tarot · Three-card spread']
        positions = ('Current situation','A task to consider','Next small action')
        for position,card in zip(positions,result['cards']):
            name,focus,tension = TAROT_EN[card['id']]
            reverse = card['reversed']
            interpretation = f'Pattern to review: {tension}. Direction to try again: {focus}.' if reverse else f'{focus}. Point to review: {tension}.'
            card.update(name=name,position=position,interpretation=interpretation)
            text.extend([f'{position} — {name} ({"reversed" if reverse else "upright"})',interpretation])
        text.extend(['Consider one action you can verify today in the context of your question.',
                     'Basis: a 78-card deck, three distinct cards, recorded orientations. These are modern reflection prompts, not translations of classical text.'])
    elif result.get('kind') == 'iching':
        number = result['hexagram']['number']
        name,theme = HEXAGRAM_EN[number-1]
        result['hexagram'].update(name=name,theme=theme)
        next_number = result['transformed']['number']
        next_name,next_theme = HEXAGRAM_EN[next_number-1]
        result['transformed']['name'] = next_name
        text = [f'I Ching · Primary hexagram {number}: {name}',f'Reflection: {theme}.']
        for i in range(5,-1,-1):
            value = result['lines'][i]
            text.append(f'Line {i+1}: {"━━━━━━" if value % 2 else "━━  ━━"}  {value}' + (' · changing' if i+1 in result['changing_lines'] else ''))
        if result['changing_lines']:
            text.extend(['Changing lines: ' + ', '.join(map(str,result['changing_lines'])),
                         f'Relating hexagram {next_number}: {next_name}. Reflection: {next_theme}.',
                         'Changing positions are shown; classical line statements are not quoted or interpreted.'])
        else:
            text.append('No changing lines. Review the current theme.')
        method = 'three independent fair coins per line' if result['coins'] is not None else 'replayed user-supplied line values'
        text.append(f'Basis: {method}, six lines bottom first, King Wen order.')
    elif 'charts' in result and result.get('day_master_relation'):
        a,b = result['charts']
        from .daily_fortune_engine import _stem_element
        relations = {'same':'the same element','output':'A generates B','input':'B generates A','wealth':'A controls B','pressure':'B controls A'}
        text = ['Two-person comparison · Bazi evidence',
                f"Day masters: A {_STEMS[a['day_master']]} ({ELEMENT_EN[_stem_element(a['day_master'])]}) · B {_STEMS[b['day_master']]} ({ELEMENT_EN[_stem_element(b['day_master'])]})",
                'Element relation: ' + relations[result['day_master_relation']] + '. This is not a good/bad relationship verdict.']
        for label,chart in zip(('A','B'),result['charts']):
            text.append(label + ' birth timezone: ' + chart.get('birth_timezone', 'Asia/Seoul')
                         + (' (default; not supplied)' if chart.get('timezone_source', 'default') == 'default' else ''))
            text.append(label + ' element counts: ' + ' · '.join(f'{ELEMENT_EN[e]} {n}' for e,n in chart['elements'].items()))
            if chart.get('uncertain_pillars'):
                text.append(label + ' unresolved solar-term pillars omitted from counts and branch comparisons: '
                            + ', '.join(chart['uncertain_pillars']) + '.')
        text.append('Cross-chart branch pairs (within-person pairs excluded):')
        pillars = {'year':'year pillar','month':'month pillar','day':'day pillar','time':'hour pillar'}
        for match in result['cross_relations']:
            relation = 'Six Harmony' if match['relation'] == '육합' else 'Six Clash'
            text.append(f"A {pillars[match['a_pillar']]} {match['branches'][0]} ↔ B {pillars[match['b_pillar']]} {match['branches'][1]}: {relation}")
        if not result['cross_relations']:
            text.append('No Six Harmony or Six Clash matches. This does not determine relationship quality.')
        text.append('Reflection: how can you coordinate pace, boundaries and decisions in everyday life?')
        if result['status'] == 'partial':
            text.append('Birth time is missing: that persons hour pillar and its elements are excluded.')
        text.extend(['Basis: one Bazi calculation per person, day-master element relation and cross-chart branch tables.',
                     'No marriage/separation verdict or relationship success probability is predicted.'])
    else:
        raise ValueError('No English presentation for this reading type')
    result['text'] = '\n'.join([*text,DISCLAIMER_EN])
    if result.get('kind') == 'iching':
        from .spoken_reading import iching_speech_text
        result['speech_text'] = iching_speech_text(result, code)
    return result
