import libtcodpy as libtcod
import shelve
import math
import textwrap
from tile import Tile 
from rect import Rect

#actual size of the window
SCREEN_WIDTH = 75
SCREEN_HEIGHT = 45 
 
#size of the map
MAP_WIDTH = 75
MAP_HEIGHT = 38
 
LEVEL_SCREEN_WIDTH = 40
CHARACTER_SCREEN_WIDTH = 30

#sizes and coordinates relevant for the GUI
BAR_WIDTH = 20
PANEL_HEIGHT = 7
PANEL_Y = SCREEN_HEIGHT - PANEL_HEIGHT

MSG_X = BAR_WIDTH + 2
MSG_WIDTH = SCREEN_WIDTH - BAR_WIDTH - 2
MSG_HEIGHT = PANEL_HEIGHT - 1

INVENTORY_WIDTH = 50

#spell values
HEAL_AMOUNT = 4
LIGHTNING_DAMAGE = 20
LIGHTNING_RANGE = 5 
CONFUSE_NUM_TURNS = 10
CONFUSE_RANGE = 8
FIREBALL_RADIUS = 3
FIREBALL_DAMAGE = 12

LEVEL_UP_BASE = 200
LEVEL_UP_FACTOR = 150

LIMIT_FPS = 20  #20 frames-per-second maximum

ROOM_MAX_SIZE = 10
ROOM_MIN_SIZE = 6
MAX_ROOMS = 30

MAX_ROOM_MONSTERS = 3
MAX_ROOM_ITEMS = 2

FOV_ALGO = 0
FOV_LIGHT_WALLS = True
TORCH_RADIUS = 10
 
color_dark_wall = libtcod.Color(0, 0, 100)
color_light_wall = libtcod.Color(130, 110, 50)
color_dark_ground = libtcod.Color(50, 50, 150)
color_light_ground = libtcod.Color(200, 180, 50)
 
class Object:
    #this is a generic object: the player, a monster, an item, the stairs...
    #it's always represented by a character on screen.
    def __init__(self, x, y, char, name, color, blocks=False, always_visible=False, fighter=None, ai=None, item=None):
        self.x = x
        self.y = y
        self.char = char
        self.name = name
        self.color = color
        self.blocks = blocks
        self.fighter = fighter
        self.always_visible = always_visible
        if self.fighter:  #let the fighter component know who owns it
            self.fighter.owner = self
 
        self.ai = ai
        if self.ai:  #let the AI component know who owns it
            self.ai.owner = self

        self.item = item
        if self.item:  #let the Item component know who owns it
            self.item.owner = self
 
    def move(self, dx, dy):
        #move by the given amount, if the destination is not blocked
        if not is_blocked(self.x + dx, self.y + dy):
            self.x += dx
            self.y += dy
 
    def move_towards(self, target_x, target_y):
        #vector from this object to the target, and distance
        dx = target_x - self.x
        dy = target_y - self.y
        distance = math.sqrt(dx ** 2 + dy ** 2)
 
        #normalize it to length 1 (preserving direction), then round it and
        #convert to integer so the movement is restricted to the map grid
        dx = int(round(dx / distance))
        dy = int(round(dy / distance))
        self.move(dx, dy)
 
    def distance_to(self, other):
        #return the distance to another object
        dx = other.x - self.x
        dy = other.y - self.y
        return math.sqrt(dx ** 2 + dy ** 2)
 
    def distance(self, x, y):
        return math.sqrt((x - self.x) ** 2 + (y - self.y) ** 2)
    def send_to_back(self):
        #make this object be drawn first, so all others appear above it if they're in the same tile.
        global objects
        objects.remove(self)
        objects.insert(0, self)
 
    def draw(self):
        #only show if it's visible to the player
        if libtcod.map_is_in_fov(fov_map, self.x, self.y) or (self.always_visible and map[self.x][self.y].explored):
            #set the color and then draw the character that represents this object at its position
            libtcod.console_set_default_foreground(con, self.color)
            libtcod.console_put_char(con, self.x, self.y, self.char, libtcod.BKGND_NONE)
 
    def clear(self):
        #erase the character that represents this object
        libtcod.console_put_char(con, self.x, self.y, ' ', libtcod.BKGND_NONE)
 
class Item:
    def __init__(self, use_function=None):
        self.use_function = use_function

    def use(self):
        #just call the "use_function" if it is defined
        if self.use_function is None:
            message('The ' + self.owner.name + ' cannot be used.')
        else:
            if self.use_function() != 'cancelled':
                inventory.remove(self.owner)  #destroy after use, unless it was cancelled for some reason

    #an item that can be picked up and used.
    def pick_up(self):
        #add to the player's inventory and remove from the map
        if len(inventory) >= 26:
            message('Your inventory is full, cannot pick up ' + self.owner.name + '.', libtcod.red)
        else:
            inventory.append(self.owner)
            objects.remove(self.owner)
            message('You picked up a ' + self.owner.name + '!', libtcod.green) 
    
    def drop(self):
        objects.append(self.owner)
        inventory.remove(self.owner)
        self.owner.x = player.x
        self.owner.y = player.y

        message('You dropped a ' + self.owner.name + '.', libtcod.yellow)

class Fighter:
    #combat-related properties and methods (monster, player, NPC).
    def __init__(self, hp, defense, power, xp, death_function=None):
        self.max_hp = hp
        self.hp = hp
        self.defense = defense
        self.power = power
        self.death_function = death_function
        self.xp = xp
 
    def attack(self, target):
        #a simple formula for attack damage
        damage = self.power - target.fighter.defense
 
        if damage > 0:
            #make the target take some damage
            message(self.owner.name.capitalize() + ' attacks ' + target.name + ' for ' + str(damage) + ' hit points.')
            target.fighter.take_damage(damage)
        else:
            message(self.owner.name.capitalize() + ' attacks ' + target.name + ' but it has no effect!')
 
    def take_damage(self, damage):
        #apply damage if possible
        if damage > 0:
            self.hp -= damage
 
            #check for death. if there's a death function, call it
            if self.hp <= 0:
                function = self.death_function
                if function is not None:
                    function(self.owner)
                    if self.owner != player:
                        player.fighter.xp += self.xp
 
    def heal(self, amount):
        #heal by the given amount, without going over the maximum
        self.hp += amount
        if self.hp > self.max_hp:
            self.hp = self.max_hp

class BasicMonster:
    #AI for a basic monster.
    def take_turn(self):
        #a basic monster takes its turn. if you can see it, it can see you
        monster = self.owner
        if libtcod.map_is_in_fov(fov_map, monster.x, monster.y):
 
            #move towards player if far away
            if monster.distance_to(player) >= 2:
                monster.move_towards(player.x, player.y)
 
            #close enough, attack! (if the player is still alive.)
            elif player.fighter.hp > 0:
                monster.fighter.attack(player)

class ConfusedMonster:
    def __init__(self, old_ai, num_turns=CONFUSE_NUM_TURNS):
        self.old_ai = old_ai
        self.num_turns = num_turns

    def take_turn(self):
        if self.num_turns > 0:
            self.owner.move(libtcod.random_get_int(0, -1, 1), libtcod.random_get_int(0, -1, 1))
            self.num_turns -= 1
        else:
            self.owner.ai = self.old_ai
            message('The ' + self.owner.name + ' is no longer confused!', libtcod.red)

def is_blocked(x, y):
    #first test the map tile
    if map[x][y].blocked:
        return True
 
    #now check for any blocking objects
    for object in objects:
        if object.blocks and object.x == x and object.y == y:
            return True
 
    return False

def create_room(room):
    global map
    
    for x in range(room.x1 + 1, room.x2):
        for y in range(room.y1 + 1, room.y2):
          map[x][y].blocked = False
          map[x][y].block_sight = False

def create_h_tunnel(x1, x2, y):
    global map
    for x in range(min(x1, x2), max(x1, x2) + 1):
        map[x][y].blocked = False
        map[x][y].block_sight = False

def create_v_tunnel(y1, y2, x):
    global map
    for y in range(min(y1, y2), max(y1, y2) + 1):
        map[x][y].blocked = False
        map[x][y].block_sight = False

def place_objects(room):
    #maximum number of monsters per room
    max_monsters = from_dungeon_level([[2, 1], [3, 4], [5, 6]])
 
    #chance of each monster
    monster_chances = {}
    monster_chances['zombie'] = 80  #orc always shows up, even if all other monsters have 0 chance
    monster_chances['ghost'] = from_dungeon_level([[15, 3], [30, 5], [60, 7]])
 
    #maximum number of items per room
    max_items = from_dungeon_level([[1, 1], [2, 4]])
 
    #chance of each item (by default they have a chance of 0 at level 1, which then goes up)
    item_chances = {}
    item_chances['heal'] = 35  #healing potion always shows up, even if all other items have 0 chance
    item_chances['lightning'] = from_dungeon_level([[25, 4]])
    item_chances['fireball'] =  from_dungeon_level([[25, 6]])
    item_chances['confuse'] =   from_dungeon_level([[10, 2]])

    #choose random number of monsters
    num_monsters = libtcod.random_get_int(0, 0, max_monsters)
 
    for i in range(num_monsters):
        x = libtcod.random_get_int(0, room.x1+1, room.x2-1)
        y = libtcod.random_get_int(0, room.y1+1, room.y2-1)

        #only place it if the tile is not blocked
        if not is_blocked(x, y):
            if random_choice(monster_chances):
                fighter_component = Fighter(hp=8, defense=0, power=3, xp=30, death_function=monster_death)
                ai_component = BasicMonster()
 
                monster = Object(x, y, 'Z', 'Zombie', libtcod.desaturated_green,
                    blocks=True, fighter=fighter_component, ai=ai_component)
            else:
                fighter_component = Fighter(hp=4, defense=1, power=4, xp=100, death_function=monster_death)
                ai_component = BasicMonster()
 
                monster = Object(x, y, 'G', 'Ghost', libtcod.darker_green,
                    blocks=True, fighter=fighter_component, ai=ai_component)
 
            objects.append(monster)

        #choose random number of items
    num_items = libtcod.random_get_int(0, 0, MAX_ROOM_ITEMS)
 
    for i in range(num_items):
        #choose random spot for this item
        x = libtcod.random_get_int(0, room.x1+1, room.x2-1)
        y = libtcod.random_get_int(0, room.y1+1, room.y2-1)
 
        #only place it if the tile is not blocked
        if not is_blocked(x, y):
            choice = random_choice(item_chances)
            if choice == 'heal':
                #create a healing potion
                item_component = Item(use_function=cast_heal)
                item = Object(x, y, '!', 'healing potion', libtcod.violet, item=item_component)
            elif choice == 'ligthning':
                item_component = Item(use_function=cast_lightning)
                item = Object(x, y, '#', 'scroll of lightning', libtcod.light_yellow, item=item_component)
            elif choice == 'fireball':
                item_component = Item(use_function=cast_fireball)
                item = Object(x, y, '#', 'scroll of fireball', libtcod.light_yellow, item=item_component)
            else:
                item_component = Item(use_function=cast_confuse)
                item = Object(x, y, '#', 'scroll of confusion', libtcod.light_yellow, item=item_component)
 
            objects.append(item)
            item.send_to_back()  #items appear below other objects
            item.always_visible = True

def make_map():
    global map, objects, stairs

    objects = [player]
 
    #fill map with "blocked" tiles
    map = [[ Tile(True)
        for y in range(MAP_HEIGHT) ]
            for x in range(MAP_WIDTH) ]
 
    rooms = []
    num_rooms = 0
 
    for r in range(MAX_ROOMS):
        #random width and height
        w = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
        h = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
        #random position without going out of the boundaries of the map
        x = libtcod.random_get_int(0, 0, MAP_WIDTH - w - 1)
        y = libtcod.random_get_int(0, 0, MAP_HEIGHT - h - 1)
 
        #"Rect" class makes rectangles easier to work with
        new_room = Rect(x, y, w, h)
 
        #run through the other rooms and see if they intersect with this one
        failed = False
        for other_room in rooms:
            if new_room.intersect(other_room):
                failed = True
                break
 
        if not failed:
            #this means there are no intersections, so this room is valid
 
            #"paint" it to the map's tiles
            create_room(new_room)
 
            #center coordinates of new room, will be useful later
            (new_x, new_y) = new_room.center()
 
            if num_rooms == 0:
                #this is the first room, where the player starts at
                player.x = new_x
                player.y = new_y
            else:
                #all rooms after the first:
                #connect it to the previous room with a tunnel
 
                #center coordinates of previous room
                (prev_x, prev_y) = rooms[num_rooms-1].center()
 
                #draw a coin (random number that is either 0 or 1)
                if libtcod.random_get_int(0, 0, 1) == 1:
                    #first move horizontally, then vertically
                    create_h_tunnel(prev_x, new_x, prev_y)
                    create_v_tunnel(prev_y, new_y, new_x)
                else:
                    #first move vertically, then horizontally
                    create_v_tunnel(prev_y, new_y, prev_x)
                    create_h_tunnel(prev_x, new_x, new_y)

            place_objects(new_room)
            #finally, append the new room to the list
            rooms.append(new_room)
            num_rooms += 1
 
    stairs = Object(new_x, new_y, '>', 'stairs', libtcod.white, always_visible=True)
    objects.append(stairs)
    stairs.send_to_back()

def next_level():
    global dungeon_level

    dungeon_level += 1
    message('You take a moment to rest and regain your strength.', libtcod.white)
    player.fighter.heal(player.fighter.max_hp / 2)

    message('After a rare moment of peace, you descend deeper into the dungeon...', libtcod.red)
    make_map()
    initialize_fov()
    libtcod.console_clear(con)

def render_all():
    global fov_map, color_dark_wall, color_light_wall
    global color_dark_ground, color_light_ground
    global fov_recompute
    global dungeon_level
 
    if fov_recompute:
        #recompute FOV if needed (the player moved or something)
        fov_recompute = False
        libtcod.map_compute_fov(fov_map, player.x, player.y, TORCH_RADIUS, FOV_LIGHT_WALLS, FOV_ALGO)
 
        #go through all tiles, and set their background color according to the FOV
        for y in range(MAP_HEIGHT):
            for x in range(MAP_WIDTH):
                visible = libtcod.map_is_in_fov(fov_map, x, y)
                wall = map[x][y].block_sight
                if not visible:
                    if map[x][y].explored:
                        #it's out of the player's FOV
                        if wall:
                            libtcod.console_set_char_background(con, x, y, color_dark_wall, libtcod.BKGND_SET)
                        else:
                            libtcod.console_set_char_background(con, x, y, color_dark_ground, libtcod.BKGND_SET)
                else:
                    #it's visible
                    if wall:
                        libtcod.console_set_char_background(con, x, y, color_light_wall, libtcod.BKGND_SET )
                    else:
                        libtcod.console_set_char_background(con, x, y, color_light_ground, libtcod.BKGND_SET )

                    map[x][y].explored = True
 
    #draw all objects in the list
    for object in objects:
        if object != player:
            object.draw()
    player.draw()
    #blit the contents of "con" to the root console
    libtcod.console_blit(con, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, 0, 0, 0)

    #prepare to render the GUI panel
    libtcod.console_set_default_background(panel, libtcod.black)
    libtcod.console_clear(panel)

    #display names of objects under the mouse
    libtcod.console_set_default_foreground(panel, libtcod.light_gray)
    libtcod.console_print_ex(panel, 1, 0, libtcod.BKGND_NONE, libtcod.LEFT, get_names_under_mouse())

    #print the game messages, one line at a time
    y = 1
    for (line, color) in game_msgs:
        libtcod.console_set_default_foreground(panel, color)
        libtcod.console_print_ex(panel, MSG_X, y, libtcod.BKGND_NONE, libtcod.LEFT, line)
        y += 1

    #show the player's stats
    render_bar(1, 1, BAR_WIDTH, 'HP', player.fighter.hp, player.fighter.max_hp, libtcod.light_red, libtcod.darker_red)
    libtcod.console_print_ex(panel, 1, 3, libtcod.BKGND_NONE, libtcod.LEFT, 'Dugeon Level ' + str(dungeon_level))

    #blit the contents of "panel" to the root console
    libtcod.console_blit(panel, 0, 0, SCREEN_WIDTH, PANEL_HEIGHT, 0, 0, PANEL_Y)

def player_move_or_attack(dx, dy):
    global fov_recompute
 
    #the coordinates the player is moving to/attacking
    x = player.x + dx
    y = player.y + dy
 
    #try to find an attackable object there
    target = None
    for object in objects:
        if object.fighter and object.x == x and object.y == y:
            target = object
            break
 
    #attack if target found, move otherwise
    if target is not None:
        player.fighter.attack(target)
    else:
        player.move(dx, dy)
        fov_recompute = True
 
def handle_keys():
    global fov_recompute
    #key = libtcod.console_check_for_keypress()  #real-time
    #key = libtcod.console_wait_for_keypress(True)  #turn-based
 
    if key.vk == libtcod.KEY_ENTER and key.lalt:
        #Alt+Enter: toggle fullscreen
        libtcod.console_set_fullscreen(not libtcod.console_is_fullscreen())
 
    elif key.vk == libtcod.KEY_ESCAPE:
        return 'exit' 

    if game_state == 'playing':
        #movement keys
        if key.vk == libtcod.KEY_UP:
            player_move_or_attack(0, -1)
        elif key.vk == libtcod.KEY_DOWN:
            player_move_or_attack(0, 1)
        elif key.vk == libtcod.KEY_LEFT:
            player_move_or_attack(-1, 0)
        elif key.vk == libtcod.KEY_RIGHT:
            player_move_or_attack(1, 0)
        else:
            #test for other keys
            key_char = chr(key.c)
            #message("Key press: " + key_char)
            if key_char == 'i':
                #show the inventory; if an item is selected, use it
                chosen_item = inventory_menu('Press the key next to an item to use it, or any other to cancel.\n')
                if chosen_item is not None:
                    chosen_item.use()
 
            if key_char == 'g':
                #pick up an item
                for object in objects:  #look for an item in the player's tile
                    if object.x == player.x and object.y == player.y and object.item:
                        object.item.pick_up()
                        break

            if key_char == 'd':
                chosen_item = inventory_menu('Press the key next to an item to use it, or any other to cancel.\n')
                if chosen_item is not None:
                    chosen_item.drop()

            if key_char == '.':
                if (stairs.x == player.x) and (stairs.y == player.y):
                    next_level()
 
            if key_char == 'c':
                #show character information
                level_up_xp = LEVEL_UP_BASE + player.level * LEVEL_UP_FACTOR
                msgbox('Character Information\n\nLevel: ' + str(player.level) + '\nExperience: ' + str(player.fighter.xp) +
                    '\nExperience to level up: ' + str(level_up_xp) + '\n\nMaximum HP: ' + str(player.fighter.max_hp) +
                    '\nAttack: ' + str(player.fighter.power) + '\nDefense: ' + str(player.fighter.defense), CHARACTER_SCREEN_WIDTH)

            return 'didnt-take-turn'

def check_level_up():
    level_up_xp = LEVEL_UP_BASE + player.level * LEVEL_UP_FACTOR
    if player.fighter.xp >= level_up_xp:
        player.level += 1
        player.fighter.xp -= level_up_xp
        message('Your battle skills  grow stronger. You reached level ' + str(player.level) + ' !', libtcod.yellow)
        
        choice = None
        while choice == None:  #keep asking until a choice is made
            choice = menu('Level up! Choose a stat to raise:\n',
                ['Constitution (+20 HP, from ' + str(player.fighter.max_hp) + ')',
                'Strength (+1 attack, from ' + str(player.fighter.power) + ')',
                'Agility (+1 defense, from ' + str(player.fighter.defense) + ')'], LEVEL_SCREEN_WIDTH)
 
        if choice == 0:
            player.fighter.max_hp += 20
            player.fighter.hp += 20
        elif choice == 1:
            player.fighter.power += 1
        elif choice == 2:
            player.fighter.defense += 1

def player_death(player):
        #the game ended!
    global game_state
    message('You died!')
    game_state = 'dead'
 
    #for added effect, transform the player into a corpse!
    player.char = '%'
    player.color = libtcod.dark_red
 
def monster_death(monster):
    #transform it into a nasty corpse! it doesn't block, can't be
    #attacked and doesn't move
    message('The ' + monster.name + ' is dead! You gain ' + str(monster.fighter.xp) + ' experience points.', libtcod.orange)
    monster.char = '%'
    monster.color = libtcod.dark_red
    monster.blocks = False
    monster.fighter = None
    monster.ai = None
    monster.name = 'remains of ' + monster.name
    monster.send_to_back()

def cast_heal():
    #heal the player
    if player.fighter.hp == player.fighter.max_hp:
        message('You are already at full health.', libtcod.red)
        return 'cancelled'
 
    message('Your wounds start to feel better!', libtcod.light_violet)
    player.fighter.heal(HEAL_AMOUNT)

def cast_lightning():
    #find closest enemy (inside a maximum range) and damage it
    monster = closest_monster(LIGHTNING_RANGE)
    if monster is None:  #no enemy found within maximum range
        message('No enemy is close enough to strike.', libtcod.red)
        return 'cancelled'
 
    #zap it!
    message('A lighting bolt strikes the ' + monster.name + ' with a loud thunder! The damage is '
        + str(LIGHTNING_DAMAGE) + ' hit points.', libtcod.light_blue)
    monster.fighter.take_damage(LIGHTNING_DAMAGE)

def cast_confuse():
    message('Left click an enemy to confuse it, or right-click to cancel.', libtcod.light_cyan)
    monster = target_monster(CONFUSE_RANGE)
    if monster is None: return 'canceled'

    old_ai = monster.ai
    monster.ai = ConfusedMonster(old_ai)
    monster.ai.owner = monster
    message('The eye of the ' + monster.name + ' look vacant, as he stumbles around!', libtcod.light_green)

def cast_fireball():
    message('Left-click a target tile for the fireball, or right-click to cancel.', libtcod.light_cyan)
    (x, y) = target_tile()
    if x is None: return 'canceled'
    message('The fireball explodes, burning everything within ' + str(FIREBALL_RADIUS) + ' tiles!', libtcod.orange)

    for obj in objects:
        if obj.distance(x, y) <= FIREBALL_RADIUS and obj.fighter:
            message('The ' + obj.name + ' gets burned for ' + str(FIREBALL_DAMAGE) + ' hit points!', libtcod.orange)
            obj.fighter.take_damage(FIREBALL_DAMAGE)

def closest_monster(max_range):
    closest_enemy = None
    closest_dist = max_range + 1

    for object in objects:
        if object.fighter and not object == player and libtcod.map_is_in_fov(fov_map, object.x, object.y):
            dist = player.distance_to(object)
            if dist < closest_dist:
                closest_enemy = object
                closest_dist = dist

    return closest_enemy

def target_tile(max_range=None):
    global key, mouse
    while True:
        libtcod.console_flush()
        libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS|libtcod.EVENT_MOUSE,key,mouse)
        render_all()

        (x, y) = mouse.cx, mouse.cy

        if(mouse.lbutton_pressed and libtcod.map_is_in_fov(fov_map, x, y)) and (max_range is None or player.distance(x,y) <= max_range):
            return(x, y)

        if mouse.rbutton_pressed or key.vk == libtcod.KEY_ESCAPE:
            return(None, None)

def target_monster(max_range=None):
    while True:
        (x, y) = target_tile(max_range)
        if x is None:
            return None

        for obj in objects:
            if obj.x == x and obj.y == y and obj.fighter and obj != player:
                return obj

def render_bar(x, y, total_width, name, value, maximum, bar_color, back_color):
    #render a bar (HP, experience, etc). first calculate the width of the bar
    bar_width = int(float(value) / maximum * total_width)
 
    #render the background first
    libtcod.console_set_default_background(panel, back_color)
    libtcod.console_rect(panel, x, y, total_width, 1, False, libtcod.BKGND_SCREEN)
 
    #now render the bar on top
    libtcod.console_set_default_background(panel, bar_color)
    if bar_width > 0:
        libtcod.console_rect(panel, x, y, bar_width, 1, False, libtcod.BKGND_SCREEN)

    #finally, some centered text with the values
    libtcod.console_set_default_foreground(panel, libtcod.white)
    libtcod.console_print_ex(panel, x + total_width // 2, y, libtcod.BKGND_NONE, libtcod.CENTER,
        name + ': ' + str(value) + '/' + str(maximum))

def from_dungeon_level(table):
    #returns a value that depends on level. the table specifies what value occurs after each level, default is 0.
    for (value, level) in reversed(table):
        if dungeon_level >= level:
            return value
    return 0

def random_choice_index(chances):  #choose one option from list of chances, returning its index
    #the dice will land on some number between 1 and the sum of the chances
    dice = libtcod.random_get_int(0, 1, sum(chances))
 
    #go through all chances, keeping the sum so far
    running_sum = 0
    choice = 0
    for w in chances:
        running_sum += w
 
        #see if the dice landed in the part that corresponds to this choice
        if dice <= running_sum:
            return choice
        choice += 1

def random_choice(chances_dict):
    #choose one option from dictionary of chances, returning its key
    chances = chances_dict.values()
    strings = chances_dict.keys()
 
    return strings[random_choice_index(chances)]

def message(new_msg, color = libtcod.white):
    #split the message if necessary, among multiple lines
    new_msg_lines = textwrap.wrap(new_msg, MSG_WIDTH)
 
    for line in new_msg_lines:
        #if the buffer is full, remove the first line to make room for the new one
        if len(game_msgs) == MSG_HEIGHT:
            del game_msgs[0]
 
        #add the new line as a tuple, with the text and the color
        game_msgs.append( (line, color) )

def get_names_under_mouse():
    global mouse

    #return a string with the names of all objects under the mouse
    (x, y) = (mouse.cx, mouse.cy)
 
    #create a list with the names of all objects at the mouse's coordinates and in FOV
    names = [obj.name for obj in objects
        if obj.x == x and obj.y == y and libtcod.map_is_in_fov(fov_map, obj.x, obj.y)]
 
    names = ', '.join(names)  #join the names, separated by commas
    return names.capitalize()

def menu(header, options, width):
    if len(options) > 26: raise ValueError('Cannot have a menu with more than 26 options.')
 
    #calculate total height for the header (after auto-wrap) and one line per option
    header_height = libtcod.console_get_height_rect(con, 0, 0, width, SCREEN_HEIGHT, header)
    if header == '':
        header_height = 0
    height = len(options) + header_height
 
    #create an off-screen console that represents the menu's window
    window = libtcod.console_new(width, height)
 
    #print the header, with auto-wrap
    libtcod.console_set_default_foreground(window, libtcod.white)
    libtcod.console_print_rect_ex(window, 0, 0, width, height, libtcod.BKGND_NONE, libtcod.LEFT, header)
 
    #print all the options
    y = header_height
    letter_index = ord('a')
    for option_text in options:
        text = '(' + chr(letter_index) + ') ' + option_text
        libtcod.console_print_ex(window, 0, y, libtcod.BKGND_NONE, libtcod.LEFT, text)
        y += 1
        letter_index += 1
 
    #blit the contents of "window" to the root console
    x = SCREEN_WIDTH/2 - width/2
    y = SCREEN_HEIGHT/2 - height/2
    libtcod.console_blit(window, 0, 0, width, height, 0, x, y, 1.0, 0.7)
 
    #present the root console to the player and wait for a key-press
    libtcod.console_flush()
    key = libtcod.console_wait_for_keypress(True)
 
    #convert the ASCII code to an index; if it corresponds to an option, return it
    index = key.c - ord('a')
    if index >= 0 and index < len(options): return index
    return None

def inventory_menu(header):
    #show a menu with each item of the inventory as an option
    if len(inventory) == 0:
        options = ['Inventory is empty.']
    else:
        options = [item.name for item in inventory]
 
    index = menu(header, options, INVENTORY_WIDTH)
 
    #if an item was chosen, return it
    if index is None or len(inventory) == 0: return None
    return inventory[index].item

def msgbox(text, width=50):
    menu(text, [], width)

def new_game():
    global player, game_state, game_msgs, inventory, dungeon_level, stairs

    #create object representing the player
    fighter_component = Fighter(hp=30, defense=2, power=5, xp=0, death_function=player_death)
    player = Object(SCREEN_WIDTH//2, SCREEN_HEIGHT//2, '@', 'Player', libtcod.white, blocks=True, fighter=fighter_component)

    player.level = 1

    #generate map (at this point it's not drawn to the screen)
    dungeon_level = 1
    make_map()
    initialize_fov()
    libtcod.console_clear(con)

    game_state = 'playing'
    inventory = []

    game_msgs = []
    message('Welcome stranger! Prepare to perish in Rise of the Dead.', libtcod.red) 

def save_game():
    file = shelve.open('savegame', 'n')
    file['map'] = map
    file['objects'] = objects
    file['player_index'] = objects.index(player)
    file['inventory'] = inventory
    file['game_msgs'] = game_msgs
    file['game_state'] = game_state
    file['dungeon_level'] = dungeon_level
    file['stairs_index'] = objects.index(stairs)
    file.close()

def load_game():
    global map, objects, player, inventory, game_msgs, game_state, dungeon_level, stairs

    file = shelve.open('savegame', 'r')
    map = file['map']
    objects = file['objects']
    player = objects[file['player_index']]
    inventory = file['inventory']
    game_msgs = file['game_msgs']
    game_state = file['game_state']
    dungeon_level = file['dungeon_level']
    stairs = objects[file['stairs_index']]
    file.close()

    initialize_fov()

def initialize_fov():
    global fov_recompute, fov_map

    fov_recompute = True

    fov_map = libtcod.map_new(MAP_WIDTH, MAP_HEIGHT)
    for y in range(MAP_HEIGHT):
        for x in range(MAP_WIDTH):
            libtcod.map_set_properties(fov_map, x, y, not map[x][y].block_sight, not map[x][y].blocked)

def play_game():
    global key, mouse
    player_action = None

    mouse = libtcod.Mouse()
    key = libtcod.Key()

    while not libtcod.console_is_window_closed():
        libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS|libtcod.EVENT_MOUSE,key,mouse)

        #render the screen
        render_all()
    
        libtcod.console_flush()
        check_level_up()
    
        #erase all objects at their old locations, before they move
        for object in objects:
            object.clear()

        player_action = handle_keys()
        if player_action == 'exit':
            save_game()
            break

        if game_state == 'playing' and player_action != 'didnt-take-turn':
            for object in objects:
               if object.ai:
                   object.ai.take_turn() 

def main_menu():
    img = libtcod.image_load('menu_background1.png')

    while not libtcod.console_is_window_closed():
        libtcod.image_blit_2x(img, 0, 0, 0)

        #show the game's title, and some credits!
        libtcod.console_set_default_foreground(0, libtcod.light_yellow)
        libtcod.console_print_ex(0, SCREEN_WIDTH/2, SCREEN_HEIGHT/2-4, libtcod.BKGND_NONE, libtcod.CENTER, 'RISE OF THE DEAD')
        libtcod.console_print_ex(0, SCREEN_WIDTH/2, SCREEN_HEIGHT-2, libtcod.BKGND_NONE, libtcod.CENTER, 'By Nate')

        choice = menu('', ['New game', 'Continue', 'Quit'], 24)

        if choice == 0:
            new_game()
            play_game()
        elif choice == 1:
            try:
                load_game()
            except:
                msgbox('\nNo saved game to load.\n', 24)
                continue
            play_game()
        elif choice == 2:
            break

# libtcod.console_set_custom_font('arial10x10.png', libtcod.FONT_TYPE_GREYSCALE | libtcod.FONT_LAYOUT_TCOD)
libtcod.console_set_custom_font('dejavu16x16_gs_tc.png', libtcod.FONT_TYPE_GREYSCALE | libtcod.FONT_LAYOUT_TCOD)
libtcod.console_init_root(SCREEN_WIDTH, SCREEN_HEIGHT, 'python/libtcod tutorial', False)
libtcod.sys_set_fps(LIMIT_FPS)
con = libtcod.console_new(SCREEN_WIDTH, SCREEN_HEIGHT)
panel = libtcod.console_new(SCREEN_WIDTH, PANEL_HEIGHT)

main_menu()