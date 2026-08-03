#!/usr/bin/env python3
"""P6: Strip all emoji/pictograms from templates, static, and Python files."""

import re, glob, os, sys

os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')

# Pattern matching all target ranges
EMOJI_RE = re.compile(r'[\U0001F300-\U0001FAFF\u2600-\u27BF\u2190-\u21FF\u2700-\u27BF]')

# Build a comprehensive replacement map: every char in target ranges -> replacement
# For U+1F300-U+1FAFF (emoji): mostly strip. Known meaningful ones get text.
# For U+2600-U+27BF (misc symbols + dingbats): map to text equivalents.
# For U+2190-U+21FF (arrows): replace with ASCII equivalents.
# For U+2700-U+27BF (dingbats): a subset already covered by U+2600-U+27BF.

def build_map():
    m = {}
    
    # ---- U+1F300..U+1FAFF emoji block ----
    # These are all decorative. A few known ones get text:
    emoji_text = {
        0x1F4A1: '',      # light bulb
        0x1F4A9: '',      # poop
        0x1F4AA: '',      # flexed biceps
        0x1F4AB: '',      # dizzy
        0x1F4AC: '',      # speech balloon -> these are in chat templates
        0x1F4AD: '',      # thought balloon
        0x1F4AE: '',      # white flower
        0x1F4AF: '',      # 100
        0x1F4B0: '',      # money
        0x1F4B1: '',      # currency exchange
        0x1F4B2: '',      # heavy dollar sign
        0x1F4B3: '',      # credit card
        0x1F4B4: '',      # yen
        0x1F4B5: '',      # dollar
        0x1F4B6: '',      # euro
        0x1F4B7: '',      # pound
        0x1F4B8: '',      # money with wings
        
        # Common decorative emoji -> text
        0x1F44D: '',      # thumbs up -> +1  (but we strip)
        0x1F44E: '',      # thumbs down
        0x1F44F: '',      # clap
        0x1F450: '',      # open hands
        0x1F451: '',      # crown
        0x1F452: '',      # woman's hat
        0x1F453: '',      # glasses
        0x1F454: '',      # necktie
        0x1F455: '',      # t-shirt
        0x1F456: '',      # jeans
        0x1F457: '',      # dress
        0x1F458: '',      # kimono
        0x1F459: '',      # bikini
        0x1F45A: '',      # woman's clothes
        0x1F45B: '',      # purse
        0x1F45C: '',      # handbag
        0x1F45D: '',      # pouch
        0x1F45E: '',      # man's shoe
        0x1F45F: '',      # athletic shoe
        
        0x1F600: '',      # grinning face
        0x1F601: '',      # beaming face
        0x1F602: '',      # tears of joy
        0x1F603: '',      # big eyes
        0x1F604: '',      # smiling eyes
        0x1F605: '',      # sweat smile
        0x1F606: '',      # satisfied
        0x1F607: '',      # innocent
        0x1F608: '',      # smirking
        0x1F609: '',      # wink
        0x1F60A: '',      # blush
        0x1F60B: '',      # yum
        0x1F60C: '',      # relieved
        0x1F60D: '',      # heart eyes
        0x1F60E: '',      # cool
        0x1F60F: '',      # smirk
        0x1F610: '',      # neutral
        0x1F611: '',      # expressionless
        0x1F612: '',      # unamused
        0x1F613: '',      # sweat
        0x1F614: '',      # pensive
        0x1F615: '',      # confused
        0x1F616: '',      # confounded
        0x1F617: '',      # kissing
        0x1F618: '',      # kissing heart
        0x1F619: '',      # kissing smiling
        0x1F61A: '',      # kissing closed
        0x1F61B: '',      # stuck out tongue
        0x1F61C: '',      # tongue wink
        0x1F61D: '',      # tongue squint
        0x1F61E: '',      # disappointed
        0x1F61F: '',      # worried
        0x1F620: '',      # angry
        0x1F621: '',      # pouting
        0x1F622: '',      # crying
        0x1F623: '',      # persevering
        0x1F624: '',      # triumph
        0x1F625: '',      # disappointed relieved
        0x1F626: '',      # frowning
        0x1F627: '',      # anguished
        0x1F628: '',      # fearful
        0x1F629: '',      # weary
        0x1F62A: '',      # sleepy
        0x1F62B: '',      # tired
        0x1F62C: '',      # grimacing
        0x1F62D: '',      # sob
        0x1F62E: '',      # open mouth
        0x1F62F: '',      # hushed
        0x1F630: '',      # screaming
        0x1F631: '',      # scream fear
        0x1F632: '',      # astonished
        0x1F633: '',      # flushed
        0x1F634: '',      # sleeping
        0x1F635: '',      # dizzy face
        0x1F636: '',      # no mouth
        0x1F637: '',      # mask
        0x1F638: '',      # cat grin
        0x1F639: '',      # cat joy
        0x1F63A: '',      # cat smile
        0x1F63B: '',      # cat heart
        0x1F63C: '',      # cat smirk
        0x1F63D: '',      # cat kiss
        0x1F63E: '',      # cat pout
        0x1F63F: '',      # cat cry
        0x1F640: '',      # cat weary
        0x1F641: '',      # slight frown
        0x1F642: '',      # slight smile
        0x1F643: '',      # upside down
        0x1F644: '',      # rolling eyes
        0x1F645: '',      # no good
        0x1F646: '',      # ok gesture
        0x1F647: '',      # bowing
        0x1F648: '',      # see no evil
        0x1F649: '',      # hear no evil
        0x1F64A: '',      # speak no evil
        0x1F64B: '',      # raising hand
        0x1F64C: '',      # raised hands
        0x1F64D: '',      # frowning person
        0x1F64E: '',      # pouting person
        0x1F64F: '',      # folded hands
        
        # Objects
        0x1F680: '',      # rocket
        0x1F681: '',      # helicopter
        0x1F682: '',      # steam locomotive
        0x1F683: '',      # railway car
        0x1F684: '',      # high-speed train
        0x1F685: '',      # bullet train
        0x1F686: '',      # train
        0x1F687: '',      # metro
        0x1F688: '',      # light rail
        0x1F689: '',      # station
        0x1F68A: '',      # tram
        0x1F68B: '',      # tram car
        0x1F68C: '',      # bus
        0x1F68D: '',      # oncoming bus
        0x1F68E: '',      # trolleybus
        0x1F68F: '',      # bus stop
        0x1F690: '',      # minibus
        
        0x1F4F1: '',      # mobile phone
        0x1F4F2: '',      # mobile phone with arrow
        0x1F4F3: '',      # vibration mode
        0x1F4F4: '',      # mobile phone off
        0x1F4F5: '',      # no mobile phones
        0x1F4F6: '',      # antenna bars
        0x1F4F7: '',      # camera
        0x1F4F8: '',      # camera with flash
        0x1F4F9: '',      # video camera
        0x1F4FA: '',      # television
        0x1F4FB: '',      # radio
        0x1F4FC: '',      # videocassette
        0x1F4FD: '',      # film projector
        0x1F4FE: '',      # portable stereo
        0x1F4FF: '',      # prayer beads
        
        # More common ones
        0x1F525: '',      # fire
        0x1F526: '',      # flashlight
        0x1F527: '',      # wrench
        0x1F528: '',      # hammer
        0x1F529: '',      # nut and bolt
        0x1F52A: '',      # kitchen knife
        0x1F52B: '',      # pistol
        0x1F52C: '',      # microscope
        0x1F52D: '',      # telescope
        0x1F52E: '',      # crystal ball
        0x1F52F: '',      # dotted six-pointed star
        0x1F530: '',      # Japanese symbol for beginner
        0x1F531: '',      # trident
        0x1F532: '',      # black square
        0x1F533: '',      # white square
        0x1F534: '',      # red circle
        0x1F535: '',      # blue circle
        0x1F536: '',      # large orange diamond
        0x1F537: '',      # large blue diamond
        0x1F538: '',      # small orange diamond
        0x1F539: '',      # small blue diamond
        0x1F53A: '',      # red triangle pointed up
        0x1F53B: '',      # red triangle pointed down
        0x1F53C: '',      # up button
        0x1F53D: '',      # down button
        
        0x1F9E0: '',      # brain
        0x1F9E1: '',      # orange heart
        0x1F9E2: '',      # billed cap
        0x1F9E3: '',      # scarf
        0x1F9E4: '',      # gloves
        0x1F9E5: '',      # coat
        0x1F9E6: '',      # socks
        0x1F9E7: '',      # red envelope
        0x1F9E8: '',      # firecracker
        0x1F9E9: '',      # jigsaw
        0x1F9EA: '',      # test tube
        0x1F9EB: '',      # petri dish
        0x1F9EC: '',      # dna
        0x1F9ED: '',      # compass
        0x1F9EE: '',      # abacus
        0x1F9EF: '',      # fire extinguisher
        0x1F9F0: '',      # toolbox
        0x1F9F1: '',      # brick
        0x1F9F2: '',      # magnet
        0x1F9F3: '',      # luggage
        0x1F9F4: '',      # lotion bottle
        0x1F9F5: '',      # thread
        0x1F9F6: '',      # yarn
        0x1F9F7: '',      # safety pin
        0x1F9F8: '',      # teddy bear
        0x1F9F9: '',      # broom
        0x1F9FA: '',      # basket
        0x1F9FB: '',      # roll of paper
        0x1F9FC: '',      # soap
        0x1F9FD: '',      # sponge
        0x1F9FE: '',      # receipt
        0x1F9FF: '',      # nazar amulet
        
        # Activities
        0x1F3C0: '',      # basketball
        0x1F3C1: '',      # chequered flag
        0x1F3C2: '',      # snowboarder
        0x1F3C3: '',      # runner
        0x1F3C4: '',      # surfer
        0x1F3C5: '',      # trophy
        0x1F3C6: '',      # sports medal
        0x1F3C7: '',      # horse racing
        0x1F3C8: '',      # football
        0x1F3C9: '',      # rugby
        0x1F3CA: '',      # swimmer
        0x1F3CB: '',      # weightlifter
        0x1F3CC: '',      # golfer
        0x1F3CD: '',      # motorcycle
        0x1F3CE: '',      # race car
        0x1F3CF: '',      # cricket
        0x1F3D0: '',      # volleyball
        0x1F3D1: '',      # field hockey
        0x1F3D2: '',      # ice hockey
        0x1F3D3: '',      # ping pong
        0x1F3D4: '',      # snow capped mountain
        0x1F3D5: '',      # camping
        0x1F3D6: '',      # beach
        0x1F3D7: '',      # building construction
        0x1F3D8: '',      # house
        0x1F3D9: '',      # cityscape
        0x1F3DA: '',      # derelict house
        0x1F3DB: '',      # classical building
        0x1F3DC: '',      # desert
        0x1F3DD: '',      # desert island
        0x1F3DE: '',      # national park
        0x1F3DF: '',      # stadium
        0x1F3E0: '',      # house
        0x1F3E1: '',      # house with garden
        0x1F3E2: '',      # office
        0x1F3E3: '',      # post office
        0x1F3E4: '',      # european post office
        0x1F3E5: '',      # hospital
        0x1F3E6: '',      # bank
        0x1F3E7: '',      # atm
        0x1F3E8: '',      # hotel
        0x1F3E9: '',      # love hotel
        0x1F3EA: '',      # convenience store
        0x1F3EB: '',      # school
        0x1F3EC: '',      # department store
        0x1F3ED: '',      # factory
        0x1F3EE: '',      # red paper lantern
        0x1F3EF: '',      # japanese castle
        0x1F3F0: '',      # european castle
        0x1F3F1: '',      # white flag
        0x1F3F2: '',      # black flag
        0x1F3F3: '',      # waving white flag
        0x1F3F4: '',      # waving black flag
        0x1F3F5: '',      # rosette
        0x1F3F6: '',      # label
        0x1F3F7: '',      # badminton
        0x1F3F8: '',      # bow and arrow
        0x1F3F9: '',      # amphora
        0x1F3FA: '',      # emoji modifier fitzpatrick
        
        # Symbols
        0x1F500: '',      # shuffle tracks
        0x1F501: '',      # repeat
        0x1F502: '',      # repeat one
        0x1F503: '',      # clockwise
        0x1F504: '',      # anticlockwise
        0x1F505: '',      # dim button
        0x1F506: '',      # bright button
        0x1F507: '',      # speaker muted
        0x1F508: '',      # speaker low
        0x1F509: '',      # speaker medium
        0x1F50A: '',      # speaker high
        0x1F50B: '',      # battery
        0x1F50C: '',      # electric plug
        0x1F50D: '',      # magnifying glass
        0x1F50E: '',      # magnifying glass right
        0x1F50F: '',      # lock with pen
        0x1F510: '',      # closed lock with key
        0x1F511: '',      # key
        0x1F512: '',      # lock
        0x1F513: '',      # unlock
        0x1F514: '',      # bell
        0x1F515: '',      # bell with slash
        0x1F516: '',      # bookmark
        0x1F517: '',      # link
        0x1F518: '',      # radio button
        0x1F519: '',      # back arrow
        0x1F51A: '',      # end arrow
        0x1F51B: '',      # on! arrow
        0x1F51C: '',      # soon arrow
        0x1F51D: '',      # top arrow
        0x1F51E: '',      # no under 18
        0x1F51F: '',      # keycap ten
    
        # Nature
        0x1F300: '',      # cyclone
        0x1F301: '',      # foggy
        0x1F302: '',      # closed umbrella
        0x1F303: '',      # night with stars
        0x1F304: '',      # sunrise over mountains
        0x1F305: '',      # sunrise
        0x1F306: '',      # cityscape at dusk
        0x1F307: '',      # sunset
        0x1F308: '',      # rainbow
        0x1F309: '',      # bridge at night
        0x1F30A: '',      # water wave
        0x1F30B: '',      # volcano
        0x1F30C: '',      # milky way
        0x1F30D: '',      # globe showing europe-africa
        0x1F30E: '',      # globe showing americas
        0x1F30F: '',      # globe showing asia-australia
        0x1F310: '',      # globe with meridians
        0x1F311: '',      # new moon
        0x1F312: '',      # waxing crescent moon
        0x1F313: '',      # first quarter moon
        0x1F314: '',      # waxing gibbous moon
        0x1F315: '',      # full moon
        0x1F316: '',      # waning gibbous moon
        0x1F317: '',      # last quarter moon
        0x1F318: '',      # waning crescent moon
        0x1F319: '',      # crescent moon
        0x1F31A: '',      # new moon face
        0x1F31B: '',      # first quarter moon face
        0x1F31C: '',      # last quarter moon face
        0x1F31D: '',      # full moon face
        0x1F31E: '',      # sun with face
        0x1F31F: '',      # glowing star
        
        # Animals
        0x1F400: '',      # rat
        0x1F401: '',      # mouse
        0x1F402: '',      # ox
        0x1F403: '',      # water buffalo
        0x1F404: '',      # cow
        0x1F405: '',      # tiger
        0x1F406: '',      # leopard
        0x1F407: '',      # rabbit
        0x1F408: '',      # cat
        0x1F409: '',      # dragon
        0x1F40A: '',      # crocodile
        0x1F40B: '',      # whale
        0x1F40C: '',      # snail
        0x1F40D: '',      # snake
        0x1F40E: '',      # horse
        0x1F40F: '',      # ram
        0x1F410: '',      # goat
        0x1F411: '',      # sheep
        0x1F412: '',      # monkey
        0x1F413: '',      # rooster
        0x1F414: '',      # chicken
        0x1F415: '',      # dog
        0x1F416: '',      # pig
        0x1F417: '',      # boar
        0x1F418: '',      # elephant
        0x1F419: '',      # octopus
        0x1F41A: '',      # spiral shell
        0x1F41B: '',      # bug
        0x1F41C: '',      # ant
        0x1F41D: '',      # honeybee
        0x1F41E: '',      # lady beetle
        0x1F41F: '',      # fish
        
        # Food
        0x1F340: '',      # four leaf clover
        0x1F341: '',      # maple leaf
        0x1F342: '',      # fallen leaf
        0x1F343: '',      # leaf fluttering
        0x1F344: '',      # mushroom
        0x1F345: '',      # tomato
        0x1F346: '',      # eggplant
        0x1F347: '',      # grapes
        0x1F348: '',      # melon
        0x1F349: '',      # watermelon
        0x1F34A: '',      # tangerine
        0x1F34B: '',      # lemon
        0x1F34C: '',      # banana
        0x1F34D: '',      # pineapple
        0x1F34E: '',      # red apple
        0x1F34F: '',      # green apple
        0x1F350: '',      # pear
        0x1F351: '',      # peach
        0x1F352: '',      # cherries
        0x1F353: '',      # strawberry
        0x1F354: '',      # hamburger
        0x1F355: '',      # pizza
        0x1F356: '',      # meat
        0x1F357: '',      # poultry leg
        0x1F358: '',      # rice cracker
        0x1F359: '',      # rice ball
        0x1F35A: '',      # cooked rice
        0x1F35B: '',      # curry
        0x1F35C: '',      # steaming bowl
        0x1F35D: '',      # spaghetti
        0x1F35E: '',      # bread
        0x1F35F: '',      # french fries
        
        # Other common
        0x1F440: '',      # eyes
        0x1F441: '',      # eye
        0x1F442: '',      # ear
        0x1F443: '',      # nose
        0x1F444: '',      # mouth
        0x1F445: '',      # tongue
        
        # Math/book
        0x1F4D0: '',      # triangular ruler
        0x1F4D1: '',      # bookmark tabs
        0x1F4D2: '',      # ledger
        0x1F4D3: '',      # notebook
        0x1F4D4: '',      # notebook with decorative cover
        0x1F4D5: '',      # closed book
        0x1F4D6: '',      # open book
        0x1F4D7: '',      # green book
        0x1F4D8: '',      # blue book
        0x1F4D9: '',      # orange book
        0x1F4DA: '',      # books
        0x1F4DB: '',      # name badge
        0x1F4DC: '',      # scroll
        
        # Writing
        0x270D: '',       # writing hand
        0x270F: '',       # pencil
        
        # People
        0x1F466: '',      # boy
        0x1F467: '',      # girl
        0x1F468: '',      # man
        0x1F469: '',      # woman
        0x1F46A: '',      # family
        0x1F46B: '',      # mw couple
        0x1F46C: '',      # mm couple
        0x1F46D: '',      # ww couple
        0x1F46E: '',      # police
        0x1F46F: '',      # bunny ears
        
        # Hands/bodies
        0x1F470: '',      # bride
        0x1F471: '',      # blond
        0x1F472: '',      # guard
        0x1F473: '',      # turban
        0x1F474: '',      # old man
        0x1F475: '',      # old woman
        0x1F476: '',      # baby
        0x1F477: '',      # construction
        0x1F478: '',      # princess
        0x1F479: '',      # ogre
        0x1F47A: '',      # goblin
        0x1F47B: '',      # ghost
        0x1F47C: '',      # baby angel
        0x1F47D: '',      # alien
        0x1F47E: '',      # alien monster
        0x1F47F: '',      # imp
        
        # Clocks
        0x1F550: '', 0x1F551: '', 0x1F552: '', 0x1F553: '', 0x1F554: '',
        0x1F555: '', 0x1F556: '', 0x1F557: '', 0x1F558: '', 0x1F559: '',
        0x1F55A: '', 0x1F55B: '', 0x1F55C: '', 0x1F55D: '', 0x1F55E: '',
        0x1F55F: '', 0x1F560: '', 0x1F561: '', 0x1F562: '', 0x1F563: '',
        0x1F564: '', 0x1F565: '', 0x1F566: '', 0x1F567: '',
        
        # Hearts/suits
        0x1F493: '', 0x1F494: '', 0x1F495: '', 0x1F496: '', 0x1F497: '',
        0x1F498: '', 0x1F499: '', 0x1F49A: '', 0x1F49B: '', 0x1F49C: '',
        0x1F49D: '', 0x1F49E: '', 0x1F49F: '',
    }
    
    # 2600-26FF: Miscellaneous Symbols
    misc = {
        0x2600: '', 0x2601: '', 0x2602: '', 0x2603: '', 0x2604: '',
        0x2605: '',   # black star
        0x2606: '',   # white star
        0x2607: '', 0x2608: '', 0x2609: '', 0x260A: '', 0x260B: '', 0x260C: '', 0x260D: '', 0x260E: '', 0x260F: '',
        0x2610: '', 0x2611: '', 0x2612: '', 0x2613: '', 0x2614: '', 0x2615: '', 0x2616: '', 0x2617: '', 0x2618: '', 0x2619: '',
        0x261A: '', 0x261B: '', 0x261C: '', 0x261D: '', 0x261E: '', 0x261F: '',
        0x2620: '', 0x2621: '', 0x2622: '', 0x2623: '', 0x2624: '', 0x2625: '', 0x2626: '', 0x2627: '', 0x2628: '', 0x2629: '',
        0x262A: '', 0x262B: '', 0x262C: '', 0x262D: '', 0x262E: '', 0x262F: '',
        0x2630: '', 0x2631: '', 0x2632: '', 0x2633: '', 0x2634: '', 0x2635: '', 0x2636: '', 0x2637: '', 0x2638: '', 0x2639: '',
        0x263A: '', 0x263B: '', 0x263C: '', 0x263D: '', 0x263E: '', 0x263F: '',
        0x2640: '', 0x2641: '', 0x2642: '', 0x2643: '', 0x2644: '', 0x2645: '', 0x2646: '', 0x2647: '', 0x2648: '', 0x2649: '',
        0x264A: '', 0x264B: '', 0x264C: '', 0x264D: '', 0x264E: '', 0x264F: '',
        0x2650: '', 0x2651: '', 0x2652: '', 0x2653: '', 0x2654: '', 0x2655: '', 0x2656: '', 0x2657: '', 0x2658: '', 0x2659: '',
        0x265A: '', 0x265B: '', 0x265C: '', 0x265D: '', 0x265E: '', 0x265F: '',
        0x2660: '', 0x2661: '', 0x2662: '', 0x2663: '', 0x2664: '', 0x2665: '', 0x2666: '', 0x2667: '', 0x2668: '', 0x2669: '',
        0x266A: '', 0x266B: '', 0x266C: '', 0x266D: '', 0x266E: '', 0x266F: '',
        0x2670: '', 0x2671: '', 0x2672: '', 0x2673: '', 0x2674: '', 0x2675: '', 0x2676: '', 0x2677: '', 0x2678: '', 0x2679: '',
        0x267A: '', 0x267B: '', 0x267C: '', 0x267D: '', 0x267E: '', 0x267F: '',
        0x2680: '', 0x2681: '', 0x2682: '', 0x2683: '', 0x2684: '', 0x2685: '', 0x2686: '', 0x2687: '', 0x2688: '', 0x2689: '',
        0x268A: '', 0x268B: '', 0x268C: '', 0x268D: '', 0x268E: '', 0x268F: '',
        0x2690: '', 0x2691: '', 0x2692: '', 0x2693: '', 0x2694: '', 0x2695: '', 0x2696: '', 0x2697: '', 0x2698: '', 0x2699: '',
        0x269A: '', 0x269B: '', 0x269C: '', 0x269D: '', 0x269E: '', 0x269F: '',
        0x26A0: '[!]',  # warning
        0x26A1: '',
        0x26A2: '', 0x26A3: '', 0x26A4: '', 0x26A5: '', 0x26A6: '', 0x26A7: '', 0x26A8: '', 0x26A9: '',
        0x26AA: '', 0x26AB: '', 0x26AC: '', 0x26AD: '', 0x26AE: '', 0x26AF: '',
        0x26B0: '', 0x26B1: '', 0x26B2: '', 0x26B3: '', 0x26B4: '', 0x26B5: '', 0x26B6: '', 0x26B7: '', 0x26B8: '', 0x26B9: '',
        0x26BA: '', 0x26BB: '', 0x26BC: '', 0x26BD: '', 0x26BE: '', 0x26BF: '',
        0x26C0: '', 0x26C1: '', 0x26C2: '', 0x26C3: '', 0x26C4: '', 0x26C5: '', 0x26C6: '', 0x26C7: '', 0x26C8: '', 0x26C9: '',
        0x26CA: '', 0x26CB: '', 0x26CC: '', 0x26CD: '', 0x26CE: '', 0x26CF: '',
        0x26D0: '', 0x26D1: '', 0x26D2: '', 0x26D3: '', 0x26D4: '', 0x26D5: '', 0x26D6: '', 0x26D7: '', 0x26D8: '', 0x26D9: '',
        0x26DA: '', 0x26DB: '', 0x26DC: '', 0x26DD: '', 0x26DE: '', 0x26DF: '',
        0x26E0: '', 0x26E1: '', 0x26E2: '', 0x26E3: '', 0x26E4: '', 0x26E5: '', 0x26E6: '', 0x26E7: '', 0x26E8: '', 0x26E9: '',
        0x26EA: '', 0x26EB: '', 0x26EC: '', 0x26ED: '', 0x26EE: '', 0x26EF: '',
        0x26F0: '', 0x26F1: '', 0x26F2: '', 0x26F3: '', 0x26F4: '', 0x26F5: '', 0x26F6: '', 0x26F7: '', 0x26F8: '', 0x26F9: '',
        0x26FA: '', 0x26FB: '', 0x26FC: '', 0x26FD: '', 0x26FE: '', 0x26FF: '',
    }
    
    # 2700-27BF: Dingbats
    dingbats = {
        0x2700: '', 0x2701: '', 0x2702: '', 0x2703: '', 0x2704: '',
        0x2705: '[OK]',     # white heavy check
        0x2706: '', 0x2707: '', 0x2708: '', 0x2709: '', 0x270A: '', 0x270B: '', 0x270C: '', 0x270D: '', 0x270E: '', 0x270F: '',
        0x2710: '', 0x2711: '', 0x2712: '', 0x2713: '[OK]',  # check
        0x2714: '[OK]',     # heavy check
        0x2715: '', 0x2716: '', 0x2717: '', 0x2718: '', 0x2719: '', 0x271A: '', 0x271B: '', 0x271C: '', 0x271D: '', 0x271E: '', 0x271F: '',
        0x2720: '', 0x2721: '', 0x2722: '', 0x2723: '', 0x2724: '', 0x2725: '', 0x2726: '', 0x2727: '', 0x2728: '', 0x2729: '',
        0x272A: '', 0x272B: '', 0x272C: '', 0x272D: '', 0x272E: '', 0x272F: '',
        0x2730: '', 0x2731: '', 0x2732: '', 0x2733: '', 0x2734: '', 0x2735: '', 0x2736: '', 0x2737: '', 0x2738: '', 0x2739: '',
        0x273A: '', 0x273B: '', 0x273C: '', 0x273D: '', 0x273E: '', 0x273F: '',
        0x2740: '', 0x2741: '', 0x2742: '', 0x2743: '', 0x2744: '', 0x2745: '', 0x2746: '', 0x2747: '', 0x2748: '', 0x2749: '',
        0x274A: '', 0x274B: '', 0x274C: '[ERROR]',  # cross
        0x274D: '', 0x274E: '[ERROR]',  # cross
        0x274F: '', 0x2750: '', 0x2751: '', 0x2752: '',
        0x2753: '',   # question mark
        0x2754: '',   # white question
        0x2755: '',   # white exclamation
        0x2756: '', 0x2757: '', 0x2758: '', 0x2759: '', 0x275A: '', 0x275B: '', 0x275C: '', 0x275D: '', 0x275E: '', 0x275F: '',
        0x2760: '', 0x2761: '', 0x2762: '', 0x2763: '', 0x2764: '', 0x2765: '', 0x2766: '', 0x2767: '', 0x2768: '', 0x2769: '',
        0x276A: '', 0x276B: '', 0x276C: '', 0x276D: '', 0x276E: '', 0x276F: '',
        0x2770: '', 0x2771: '', 0x2772: '', 0x2773: '', 0x2774: '', 0x2775: '', 0x2776: '', 0x2777: '', 0x2778: '', 0x2779: '',
        0x277A: '', 0x277B: '', 0x277C: '', 0x277D: '', 0x277E: '', 0x277F: '',
        0x2780: '', 0x2781: '', 0x2782: '', 0x2783: '', 0x2784: '', 0x2785: '', 0x2786: '', 0x2787: '', 0x2788: '', 0x2789: '',
        0x278A: '', 0x278B: '', 0x278C: '', 0x278D: '', 0x278E: '', 0x278F: '',
        0x2790: '', 0x2791: '', 0x2792: '', 0x2793: '', 0x2794: '', 0x2795: '', 0x2796: '', 0x2797: '', 0x2798: '', 0x2799: '',
        0x279A: '', 0x279B: '', 0x279C: '', 0x279D: '', 0x279E: '', 0x279F: '',
        0x27A0: '', 0x27A1: '', 0x27A2: '', 0x27A3: '', 0x27A4: '', 0x27A5: '', 0x27A6: '', 0x27A7: '', 0x27A8: '', 0x27A9: '',
        0x27AA: '', 0x27AB: '', 0x27AC: '', 0x27AD: '', 0x27AE: '', 0x27AF: '',
        0x27B0: '', 0x27B1: '', 0x27B2: '', 0x27B3: '', 0x27B4: '', 0x27B5: '', 0x27B6: '', 0x27B7: '', 0x27B8: '', 0x27B9: '',
        0x27BA: '', 0x27BB: '', 0x27BC: '', 0x27BD: '', 0x27BE: '', 0x27BF: '',
    }
    
    # Arrows 2190-21FF
    arrows = {
        0x2190: '<-', 0x2191: '^',  0x2192: '->', 0x2193: 'v',
        0x2194: '<->', 0x2195: '', 0x2196: '', 0x2197: '', 0x2198: '', 0x2199: '',
        0x219A: '', 0x219B: '', 0x219C: '', 0x219D: '', 0x219E: '', 0x219F: '',
        0x21A0: '', 0x21A1: '', 0x21A2: '', 0x21A3: '', 0x21A4: '', 0x21A5: '', 0x21A6: '', 0x21A7: '', 0x21A8: '', 0x21A9: '',
        0x21AA: '', 0x21AB: '', 0x21AC: '', 0x21AD: '', 0x21AE: '', 0x21AF: '',
        0x21B0: '', 0x21B1: '', 0x21B2: '', 0x21B3: '', 0x21B4: '', 0x21B5: '', 0x21B6: '', 0x21B7: '', 0x21B8: '', 0x21B9: '',
        0x21BA: '', 0x21BB: '', 0x21BC: '', 0x21BD: '', 0x21BE: '', 0x21BF: '',
        0x21C0: '', 0x21C1: '', 0x21C2: '', 0x21C3: '', 0x21C4: '', 0x21C5: '', 0x21C6: '', 0x21C7: '', 0x21C8: '', 0x21C9: '',
        0x21CA: '', 0x21CB: '', 0x21CC: '', 0x21CD: '', 0x21CE: '', 0x21CF: '',
        0x21D0: '', 0x21D1: '', 0x21D2: '', 0x21D3: '', 0x21D4: '', 0x21D5: '', 0x21D6: '', 0x21D7: '', 0x21D8: '', 0x21D9: '',
        0x21DA: '', 0x21DB: '', 0x21DC: '', 0x21DD: '', 0x21DE: '', 0x21DF: '',
        0x21E0: '', 0x21E1: '', 0x21E2: '', 0x21E3: '', 0x21E4: '', 0x21E5: '', 0x21E6: '', 0x21E7: '', 0x21E8: '', 0x21E9: '',
        0x21EA: '', 0x21EB: '', 0x21EC: '', 0x21ED: '', 0x21EE: '', 0x21EF: '',
        0x21F0: '', 0x21F1: '', 0x21F2: '', 0x21F3: '', 0x21F4: '', 0x21F5: '', 0x21F6: '', 0x21F7: '', 0x21F8: '', 0x21F9: '',
        0x21FA: '', 0x21FB: '', 0x21FC: '', 0x21FD: '', 0x21FE: '', 0x21FF: '',
    }
    
    # Merge all maps
    for cp in range(0x1F300, 0x1FAFF + 1):
        m[chr(cp)] = emoji_text.get(cp, '')
    for cp in range(0x2600, 0x2700):
        m[chr(cp)] = misc.get(cp, '')
    for cp in range(0x2700, 0x27C0):
        m[chr(cp)] = dingbats.get(cp, '')
    for cp in range(0x2190, 0x21FF + 1):
        m[chr(cp)] = arrows.get(cp, '')
    
    return m

REPLACE_MAP = build_map()

def clean_text(text):
    """Remove all emoji/pictograms, replacing known ones with text equivalents."""
    result = []
    for ch in text:
        replacement = REPLACE_MAP.get(ch, None)
        if replacement is None:
            result.append(ch)
        else:
            result.append(replacement)
    return ''.join(result)

# Find and process files
targets = (glob.glob('templates/**/*.html', recursive=True) +
           glob.glob('static/**/*.js', recursive=True) +
           glob.glob('static/**/*.css', recursive=True) +
           glob.glob('**/*.py', recursive=True))

changed = []
for path in targets:
    normalized = path.replace('\\', '/')
    if 'group_chats' in normalized or '.env' in normalized or '/.git/' in normalized:
        continue
    if '.pyc' in path or '__pycache__' in path:
        continue
    try:
        with open(path, encoding='utf-8', errors='ignore') as f:
            original = f.read()
    except Exception:
        continue
    if not EMOJI_RE.search(original):
        continue
    cleaned = clean_text(original)
    if cleaned != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(cleaned)
        changed.append(path)

print(f'Files changed: {len(changed)}')
for p in sorted(changed):
    print(p)
