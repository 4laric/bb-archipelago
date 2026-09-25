using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using SoulsFormats;

internal static class CharacterFfxRequirementTests
{
    static readonly CharacterFfxRequirements.Witness[] OrphanCoreWitnesses = [
        new(0L, 5, 100UL, 6480L, 645400),
        new(3000L, 28, 96UL, 72144L, 645410),
        new(3001L, 29, 96UL, 76720L, 645410),
        new(3002L, 31, 96UL, 81536L, 645410),
        new(3003L, 45, 96UL, 86768L, 645410),
        new(3004L, 29, 96UL, 91328L, 645410),
        new(3005L, 5, 96UL, 96016L, 645410),
        new(3006L, 7, 96UL, 101520L, 645410),
        new(3007L, 17, 96UL, 107216L, 645410),
        new(3008L, 0, 96UL, 111904L, 645410),
        new(3009L, 34, 96UL, 118464L, 645410),
        new(3010L, 19, 96UL, 123952L, 645410),
        new(3011L, 32, 96UL, 130864L, 645410),
        new(3012L, 65, 96UL, 139920L, 645410),
        new(3014L, 33, 96UL, 152448L, 645410),
        new(3014L, 36, 96UL, 152544L, 645410),
        new(3014L, 39, 96UL, 152640L, 645410),
        new(3015L, 9, 96UL, 158464L, 645410),
        new(3016L, 7, 96UL, 162976L, 645410),
        new(3017L, 35, 96UL, 167680L, 645410),
        new(3018L, 31, 96UL, 171840L, 645410),
        new(3020L, 17, 96UL, 177648L, 645404),
        new(3021L, 0, 96UL, 180000L, 645405),
        new(3023L, 0, 96UL, 182752L, 645405),
        new(3024L, 10, 96UL, 186416L, 645410),
        new(3025L, 6, 96UL, 191184L, 645410),
        new(3026L, 19, 96UL, 196304L, 645405),
        new(3027L, 25, 96UL, 199232L, 645420),
        new(3028L, 34, 96UL, 203120L, 645410),
        new(3031L, 5, 96UL, 207952L, 645430),
    ];

    static readonly CharacterFfxRequirements.Witness[] OrphanPhaseWitnesses = [
        new(0L, 0, 100UL, 7480L, 645401),
        new(2200L, 8, 96UL, 69136L, 650090),
        new(2200L, 9, 96UL, 69168L, 650091),
        new(2200L, 11, 96UL, 69232L, 650091),
        new(2200L, 14, 96UL, 69328L, 650091),
        new(2200L, 17, 96UL, 69424L, 650091),
        new(2200L, 19, 96UL, 69488L, 650091),
        new(2200L, 21, 96UL, 69552L, 650091),
        new(2501L, 8, 96UL, 78592L, 650090),
        new(2501L, 10, 96UL, 78656L, 650091),
        new(2501L, 12, 96UL, 78720L, 650091),
        new(2501L, 13, 96UL, 78752L, 650091),
        new(2501L, 14, 96UL, 78784L, 650091),
        new(2501L, 17, 96UL, 78880L, 650091),
        new(2501L, 18, 96UL, 78912L, 650091),
        new(2511L, 8, 96UL, 87024L, 650090),
        new(2511L, 10, 96UL, 87088L, 650091),
        new(2511L, 12, 96UL, 87152L, 650091),
        new(2511L, 15, 96UL, 87248L, 650091),
        new(2511L, 16, 96UL, 87280L, 650091),
        new(2511L, 17, 96UL, 87312L, 650091),
        new(2511L, 18, 96UL, 87344L, 650091),
        new(3000L, 17, 96UL, 91504L, 645411),
        new(3001L, 43, 96UL, 98128L, 645411),
        new(3002L, 14, 96UL, 103184L, 645411),
        new(3002L, 20, 96UL, 103376L, 645411),
        new(3003L, 18, 96UL, 110544L, 645411),
        new(3004L, 32, 96UL, 117040L, 645411),
        new(3005L, 15, 96UL, 123632L, 645411),
        new(3006L, 15, 96UL, 129808L, 645411),
        new(3007L, 14, 96UL, 134336L, 645411),
        new(3008L, 10, 96UL, 138640L, 645411),
        new(3009L, 21, 96UL, 144256L, 645411),
        new(3009L, 24, 96UL, 144352L, 645411),
        new(3010L, 8, 96UL, 149616L, 645411),
        new(3011L, 10, 96UL, 154320L, 645411),
        new(3012L, 15, 96UL, 159184L, 645411),
        new(3013L, 23, 96UL, 164608L, 645411),
        new(3014L, 17, 96UL, 170448L, 645411),
        new(3014L, 21, 96UL, 170576L, 645411),
        new(3015L, 15, 96UL, 176624L, 645411),
        new(3016L, 10, 96UL, 182752L, 645411),
        new(3017L, 2, 96UL, 188240L, 645411),
        new(3018L, 12, 96UL, 194032L, 645411),
        new(3018L, 14, 96UL, 194096L, 645411),
        new(3018L, 16, 96UL, 194160L, 645411),
        new(3020L, 23, 96UL, 205184L, 645404),
        new(3021L, 51, 96UL, 210528L, 645404),
        new(3022L, 64, 96UL, 216720L, 645404),
        new(3023L, 55, 96UL, 222912L, 645404),
        new(3024L, 1, 96UL, 226608L, 645420),
        new(3024L, 43, 96UL, 227952L, 645404),
        new(3026L, 29, 96UL, 232128L, 645411),
        new(3030L, 3, 96UL, 235440L, 650008),
        new(3030L, 5, 96UL, 235504L, 640800),
    ];

    static readonly CharacterFfxRequirements.Witness[] LudwigWitnesses = [
        new(0L, 0, 100UL, 11464L, 645100),
        new(0L, 6, 100UL, 11648L, 645101),
        new(200L, 6, 96UL, 13056L, 1031000),
        new(201L, 7, 96UL, 15008L, 1031000),
        new(202L, 5, 96UL, 16896L, 1031000),
        new(203L, 6, 96UL, 18864L, 1031000),
        new(500L, 7, 96UL, 20832L, 1031000),
        new(701L, 2, 96UL, 29872L, 1031000),
        new(702L, 1, 96UL, 33696L, 1031000),
        new(703L, 2, 96UL, 37600L, 1031000),
        new(1500L, 1, 96UL, 40624L, 1031000),
        new(2200L, 5, 96UL, 63648L, 650090),
        new(2200L, 6, 96UL, 63680L, 650091),
        new(2200L, 8, 96UL, 63744L, 650091),
        new(2200L, 10, 96UL, 63808L, 650091),
        new(2200L, 12, 96UL, 63872L, 650091),
        new(2200L, 14, 96UL, 63936L, 650091),
        new(2200L, 15, 96UL, 63968L, 650091),
        new(2200L, 17, 96UL, 64032L, 650091),
        new(2200L, 19, 96UL, 64096L, 650091),
        new(2550L, 41, 96UL, 71072L, 645179),
        new(2551L, 21, 96UL, 75600L, 650090),
        new(2551L, 22, 96UL, 75632L, 650091),
        new(2551L, 23, 96UL, 75664L, 650091),
        new(2551L, 24, 96UL, 75696L, 650091),
        new(2551L, 25, 96UL, 75728L, 650091),
        new(2551L, 26, 96UL, 75760L, 650091),
        new(2551L, 27, 96UL, 75792L, 650091),
        new(2551L, 28, 96UL, 75824L, 650091),
        new(2551L, 29, 96UL, 75856L, 650091),
        new(3000L, 43, 96UL, 81536L, 1040307),
        new(3000L, 44, 96UL, 81568L, 645116),
        new(3000L, 49, 96UL, 81728L, 645111),
        new(3000L, 50, 96UL, 81760L, 645141),
        new(3001L, 39, 96UL, 87584L, 1040303),
        new(3001L, 40, 96UL, 87616L, 645116),
        new(3001L, 46, 96UL, 87808L, 645111),
        new(3001L, 47, 96UL, 87840L, 645146),
        new(3002L, 22, 96UL, 93760L, 645144),
        new(3002L, 23, 96UL, 93792L, 645111),
        new(3002L, 39, 96UL, 94304L, 1040307),
        new(3002L, 40, 96UL, 94336L, 1040303),
        new(3002L, 41, 96UL, 94368L, 645116),
        new(3002L, 42, 96UL, 94400L, 645116),
        new(3002L, 71, 96UL, 95328L, 645142),
        new(3003L, 40, 96UL, 101088L, 1040303),
        new(3003L, 41, 96UL, 101120L, 645117),
        new(3003L, 46, 96UL, 101280L, 645111),
        new(3003L, 47, 96UL, 101312L, 645143),
        new(3004L, 39, 96UL, 107264L, 1031000),
        new(3004L, 41, 96UL, 107328L, 1031002),
        new(3004L, 42, 96UL, 107360L, 645116),
        new(3005L, 48, 96UL, 114432L, 645144),
        new(3005L, 50, 96UL, 114496L, 1040307),
        new(3005L, 51, 96UL, 114528L, 1040307),
        new(3005L, 52, 96UL, 114560L, 645117),
        new(3005L, 53, 96UL, 114592L, 645116),
        new(3005L, 59, 96UL, 114784L, 645144),
        new(3006L, 61, 96UL, 122432L, 1040301),
        new(3008L, 62, 96UL, 137312L, 1040307),
        new(3008L, 63, 96UL, 137344L, 1040303),
        new(3008L, 64, 96UL, 137376L, 645116),
        new(3008L, 65, 96UL, 137408L, 645116),
        new(3008L, 66, 96UL, 137440L, 645116),
        new(3009L, 42, 96UL, 145408L, 1040303),
        new(3009L, 43, 96UL, 145440L, 645116),
        new(3009L, 87, 96UL, 146848L, 645111),
        new(3009L, 88, 96UL, 146880L, 645145),
        new(3010L, 123, 96UL, 159440L, 1040300),
        new(3010L, 124, 96UL, 159472L, 1040300),
        new(3010L, 125, 96UL, 159504L, 1040300),
        new(3010L, 126, 96UL, 159536L, 1040300),
        new(3010L, 127, 96UL, 159568L, 1040300),
        new(3010L, 166, 96UL, 160816L, 645108),
        new(3010L, 167, 96UL, 160848L, 645108),
        new(3010L, 168, 96UL, 160880L, 645108),
        new(3010L, 169, 96UL, 160912L, 645108),
        new(3010L, 170, 96UL, 160944L, 645108),
        new(3011L, 40, 96UL, 167408L, 645104),
        new(3011L, 41, 96UL, 167440L, 645105),
        new(3011L, 42, 96UL, 167472L, 645108),
        new(3012L, 2, 96UL, 172048L, 1040302),
        new(3012L, 52, 96UL, 173648L, 645108),
        new(3014L, 62, 96UL, 186192L, 1031000),
        new(3015L, 48, 96UL, 193456L, 645104),
        new(3015L, 49, 96UL, 193488L, 645105),
        new(3015L, 50, 96UL, 193520L, 645108),
        new(3018L, 103, 96UL, 214576L, 645108),
        new(3022L, 41, 96UL, 221328L, 1040307),
        new(3022L, 42, 96UL, 221360L, 1040303),
        new(3022L, 43, 96UL, 221392L, 645116),
        new(3022L, 44, 96UL, 221424L, 645116),
        new(3022L, 64, 96UL, 222064L, 645144),
        new(3022L, 65, 96UL, 222096L, 645111),
        new(3022L, 66, 96UL, 222128L, 645142),
        new(3023L, 3, 96UL, 227040L, 1040303),
        new(3023L, 8, 96UL, 227200L, 645116),
        new(3023L, 49, 96UL, 228512L, 645111),
        new(3023L, 50, 96UL, 228544L, 645143),
        new(7001L, 41, 96UL, 234688L, 645179),
        new(7002L, 1, 96UL, 239936L, 645180),
        new(7002L, 16, 96UL, 240400L, 645180),
        new(7004L, 17, 96UL, 246352L, 645180),
        new(7004L, 20, 96UL, 246432L, 645180),
        new(1000000L, 4, 100UL, 250416L, 645102),
        new(1000200L, 0, 96UL, 251560L, 1031000),
        new(1000201L, 0, 96UL, 253456L, 1031000),
        new(1000202L, 0, 96UL, 255376L, 1031000),
        new(1000203L, 0, 96UL, 257272L, 1031000),
        new(1000701L, 16, 96UL, 266768L, 1031000),
        new(1000702L, 16, 96UL, 270336L, 1031000),
        new(1000703L, 16, 96UL, 274016L, 1031000),
        new(1002200L, 8, 96UL, 294832L, 650090),
        new(1002200L, 9, 96UL, 294864L, 650091),
        new(1002200L, 17, 96UL, 295120L, 650091),
        new(1002200L, 19, 96UL, 295184L, 650091),
        new(1002200L, 20, 96UL, 295216L, 650091),
        new(1002200L, 23, 96UL, 295312L, 650091),
        new(1002200L, 25, 96UL, 295376L, 650091),
        new(1002200L, 27, 96UL, 295440L, 650091),
        new(1002200L, 29, 96UL, 295504L, 650091),
        new(1002550L, 63, 96UL, 303888L, 645179),
        new(1002551L, 8, 96UL, 307792L, 650090),
        new(1002551L, 10, 96UL, 307856L, 650091),
        new(1002551L, 16, 96UL, 308064L, 650091),
        new(1002551L, 21, 96UL, 308224L, 650091),
        new(1002551L, 22, 96UL, 308256L, 650091),
        new(1002551L, 26, 96UL, 308384L, 650091),
        new(1002551L, 27, 96UL, 308416L, 650091),
        new(1002551L, 29, 96UL, 308480L, 650091),
        new(1002551L, 31, 96UL, 308544L, 650091),
        new(1003000L, 2, 118UL, 312688L, 645115),
        new(1003000L, 40, 96UL, 313920L, 1040304),
        new(1003000L, 41, 96UL, 313952L, 645160),
        new(1003000L, 42, 96UL, 313984L, 645143),
        new(1003001L, 2, 118UL, 318208L, 645115),
        new(1003001L, 6, 96UL, 318336L, 645111),
        new(1003001L, 41, 96UL, 319472L, 1040307),
        new(1003001L, 42, 96UL, 319504L, 645160),
        new(1003001L, 43, 96UL, 319536L, 645141),
        new(1003002L, 2, 118UL, 323664L, 645115),
        new(1003002L, 7, 96UL, 323824L, 1031002),
        new(1003002L, 36, 96UL, 324768L, 645160),
        new(1003002L, 38, 96UL, 324832L, 645162),
        new(1003003L, 2, 118UL, 329376L, 645119),
        new(1003003L, 11, 96UL, 329664L, 645111),
        new(1003003L, 41, 96UL, 330640L, 1040307),
        new(1003003L, 42, 96UL, 330672L, 645120),
        new(1003003L, 43, 96UL, 330704L, 645161),
        new(1003003L, 44, 96UL, 330736L, 645141),
        new(1003004L, 35, 96UL, 336256L, 1040303),
        new(1003004L, 36, 96UL, 336288L, 645118),
        new(1003004L, 37, 118UL, 336320L, 645119),
        new(1003004L, 38, 96UL, 336352L, 645161),
        new(1003004L, 39, 96UL, 336384L, 645143),
        new(1003005L, 5, 96UL, 340800L, 645111),
        new(1003005L, 32, 96UL, 341680L, 1040308),
        new(1003005L, 33, 96UL, 341712L, 645118),
        new(1003005L, 34, 118UL, 341744L, 645119),
        new(1003005L, 35, 96UL, 341776L, 645161),
        new(1003006L, 2, 118UL, 346304L, 645115),
        new(1003006L, 6, 96UL, 346432L, 645112),
        new(1003006L, 34, 96UL, 347344L, 1040307),
        new(1003006L, 35, 96UL, 347376L, 645160),
        new(1003006L, 36, 96UL, 347408L, 645141),
        new(1003007L, 2, 118UL, 351520L, 645115),
        new(1003007L, 7, 96UL, 351664L, 1031002),
        new(1003007L, 36, 96UL, 352608L, 645160),
        new(1003007L, 38, 96UL, 352672L, 645162),
        new(1003008L, 1, 118UL, 357744L, 645115),
        new(1003008L, 5, 118UL, 357872L, 645115),
        new(1003008L, 54, 96UL, 359440L, 645160),
        new(1003008L, 55, 96UL, 359472L, 645160),
        new(1003008L, 58, 96UL, 359568L, 645162),
        new(1003008L, 59, 96UL, 359600L, 645162),
        new(1003009L, 5, 96UL, 364288L, 645111),
        new(1003009L, 35, 96UL, 365264L, 1040302),
        new(1003009L, 36, 96UL, 365296L, 645118),
        new(1003009L, 37, 118UL, 365328L, 645119),
        new(1003009L, 38, 96UL, 365360L, 645161),
        new(1003010L, 11, 96UL, 369904L, 1031002),
        new(1003010L, 22, 96UL, 370256L, 645120),
        new(1003010L, 38, 96UL, 370784L, 1040300),
        new(1003010L, 39, 118UL, 370816L, 645119),
        new(1003010L, 41, 96UL, 370880L, 645127),
        new(1003011L, 7, 96UL, 376064L, 645111),
        new(1003011L, 40, 96UL, 377136L, 1040307),
        new(1003011L, 42, 118UL, 377200L, 645115),
        new(1003011L, 45, 118UL, 377296L, 645115),
        new(1003011L, 46, 96UL, 377328L, 645160),
        new(1003011L, 47, 96UL, 377360L, 645160),
        new(1003012L, 2, 118UL, 381872L, 645115),
        new(1003012L, 7, 96UL, 382032L, 645111),
        new(1003012L, 19, 96UL, 382432L, 645143),
        new(1003012L, 34, 96UL, 382912L, 1040303),
        new(1003012L, 36, 96UL, 382976L, 645160),
        new(1003013L, 2, 118UL, 387184L, 645115),
        new(1003013L, 5, 96UL, 387280L, 645160),
        new(1003013L, 12, 96UL, 387504L, 645111),
        new(1003013L, 20, 96UL, 387776L, 645141),
        new(1003013L, 37, 96UL, 388320L, 1040307),
        new(1003015L, 1, 118UL, 395312L, 645115),
        new(1003015L, 4, 118UL, 395408L, 645115),
        new(1003015L, 10, 96UL, 395600L, 645111),
        new(1003015L, 12, 96UL, 395664L, 645111),
        new(1003015L, 15, 96UL, 395760L, 645111),
        new(1003015L, 78, 96UL, 397792L, 1040304),
        new(1003015L, 79, 96UL, 397824L, 1040307),
        new(1003015L, 80, 96UL, 397856L, 1040308),
        new(1003015L, 81, 96UL, 397888L, 645118),
        new(1003015L, 82, 96UL, 397920L, 645160),
        new(1003015L, 83, 96UL, 397952L, 645160),
        new(1003015L, 84, 118UL, 397984L, 645119),
        new(1003015L, 85, 118UL, 398016L, 645119),
        new(1003015L, 86, 96UL, 398048L, 645161),
        new(1003015L, 87, 96UL, 398080L, 645161),
        new(1003015L, 88, 96UL, 398112L, 645143),
        new(1003015L, 89, 96UL, 398144L, 645141),
        new(1003015L, 91, 96UL, 398208L, 645162),
        new(1003016L, 1, 118UL, 405168L, 645115),
        new(1003016L, 5, 96UL, 405296L, 645160),
        new(1003016L, 12, 96UL, 405520L, 645143),
        new(1003016L, 49, 96UL, 406720L, 1040303),
        new(1003017L, 5, 96UL, 411056L, 645120),
        new(1003017L, 13, 96UL, 411312L, 645130),
        new(1003018L, 12, 96UL, 416864L, 645150),
        new(1003018L, 41, 118UL, 417808L, 645119),
        new(1003018L, 46, 96UL, 417968L, 645161),
        new(1003019L, 3, 118UL, 423840L, 645115),
        new(1003019L, 9, 96UL, 424032L, 645112),
        new(1003019L, 38, 96UL, 424960L, 1040308),
        new(1003019L, 39, 96UL, 424992L, 1040308),
        new(1003019L, 42, 96UL, 425104L, 645160),
        new(1003020L, 1, 96UL, 430128L, 645120),
        new(1003020L, 4, 96UL, 430224L, 645120),
        new(1003020L, 26, 118UL, 430944L, 645119),
        new(1003020L, 29, 118UL, 431040L, 645119),
        new(1003020L, 36, 96UL, 431264L, 645161),
        new(1003020L, 38, 96UL, 431328L, 645161),
        new(1003021L, 3, 96UL, 436640L, 1040307),
        new(1003021L, 7, 96UL, 436768L, 645160),
        new(1003021L, 45, 118UL, 438000L, 645115),
        new(1003021L, 47, 96UL, 438064L, 645141),
        new(1003023L, 36, 96UL, 443760L, 1040307),
        new(1003023L, 37, 96UL, 443792L, 645120),
        new(1003023L, 38, 118UL, 443824L, 645119),
        new(1003023L, 39, 96UL, 443856L, 645161),
        new(1003023L, 40, 96UL, 443888L, 645111),
        new(1003023L, 41, 96UL, 443920L, 645141),
        new(1003024L, 22, 96UL, 449600L, 1040303),
        new(1003024L, 26, 96UL, 449728L, 645118),
        new(1003024L, 30, 118UL, 449856L, 645119),
        new(1003024L, 33, 96UL, 449952L, 645161),
        new(1003024L, 35, 96UL, 450016L, 645143),
        new(1003027L, 26, 118UL, 455504L, 645115),
        new(1003027L, 29, 96UL, 455600L, 645160),
        new(1003027L, 32, 96UL, 455696L, 1031002),
        new(1003027L, 36, 96UL, 455824L, 645162),
        new(1003029L, 16, 96UL, 460672L, 1040302),
        new(1003029L, 17, 96UL, 460704L, 645118),
        new(1003029L, 18, 118UL, 460736L, 645119),
        new(1003029L, 19, 96UL, 460768L, 645161),
        new(1003029L, 20, 96UL, 460800L, 645111),
        new(1007002L, 57, 96UL, 470160L, 645179),
        new(1007003L, 43, 96UL, 475616L, 645179),
    ];

    internal static void Run()
    {
        var json = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
        int assertions = 0;
        void Need(bool value, string message) { assertions++; if (!value) throw new Exception(message); }
        void Refused(Action action, string fragment) {
            try { action(); throw new Exception("expected character FFX refusal: " + fragment); }
            catch (InvalidDataException error) { Need(error.Message.Contains(fragment), error.Message); }
        }
        string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        string root = Path.Combine(Path.GetTempPath(), "bb-character-ffx-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try {
            string characters = Path.Combine(root, "characters"), plan = Path.Combine(root, "plan.json");
            Directory.CreateDirectory(characters);

            (byte[] Bytes, List<CharacterFfxRequirements.Witness> Witnesses) TAE(
                params (long Animation, (ulong Type, int Effect)[] Events)[] animations) =>
                TAEFor(new ulong[] {96, 100, 118}, animations);
            (byte[] Bytes, List<CharacterFfxRequirements.Witness> Witnesses) TAEFor(
                IReadOnlyCollection<ulong> decodedEventTypes,
                params (long Animation, (ulong Type, int Effect)[] Events)[] animations)
            {
                const int animationTable = 0x60, bodySize = 40, eventSize = 24, dataSize = 24;
                int bodies = animationTable + animations.Length * 16;
                int eventTables = bodies + animations.Length * bodySize;
                int eventTotal = animations.Sum(animation => animation.Events.Length);
                int dataTables = eventTables + eventTotal * eventSize;
                byte[] bytes = new byte[dataTables + eventTotal * dataSize];
                new byte[] {0x54, 0x41, 0x45, 0x20, 0, 0, 0, 0xff}.CopyTo(bytes, 0);
                BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(8, 4), 0x1000c);
                BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(0x54, 4), animations.Length);
                BinaryPrimitives.WriteInt64LittleEndian(bytes.AsSpan(0x58, 8), animationTable);
                int eventBase = 0, dataBase = 0;
                var witnesses = new List<CharacterFfxRequirements.Witness>();
                for (int animationIndex = 0; animationIndex < animations.Length; animationIndex++) {
                    var animation = animations[animationIndex];
                    int animationRow = animationTable + animationIndex * 16;
                    int body = bodies + animationIndex * bodySize;
                    int eventTable = eventTables + eventBase * eventSize;
                    BinaryPrimitives.WriteInt64LittleEndian(bytes.AsSpan(animationRow, 8), animation.Animation);
                    BinaryPrimitives.WriteInt64LittleEndian(bytes.AsSpan(animationRow + 8, 8), body);
                    BinaryPrimitives.WriteInt64LittleEndian(bytes.AsSpan(body, 8), eventTable);
                    BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(body + 32, 4), animation.Events.Length);
                    for (int eventIndex = 0; eventIndex < animation.Events.Length; eventIndex++) {
                        var item = animation.Events[eventIndex];
                        int eventRow = eventTable + eventIndex * eventSize;
                        int data = dataTables + dataBase * dataSize;
                        BinaryPrimitives.WriteInt64LittleEndian(bytes.AsSpan(eventRow + 16, 8), data);
                        BinaryPrimitives.WriteUInt64LittleEndian(bytes.AsSpan(data, 8), item.Type);
                        BinaryPrimitives.WriteInt64LittleEndian(bytes.AsSpan(data + 8, 8), data + 16);
                        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(data + 16, 4), item.Effect);
                        if (decodedEventTypes.Contains(item.Type))
                            witnesses.Add(new(animation.Animation, eventIndex, item.Type, data + 16, item.Effect));
                        dataBase++;
                    }
                    eventBase += animation.Events.Length;
                }
                return (bytes, witnesses);
            }

            string WriteMultiBinder(string character,
                params (int EntryId, string EntryName, byte[] Tae)[] entries)
            {
                var binder = new BND4 { Compression = DCX.Type.DCX_DFLT_10000_44_9, Version = "CHARFFX1" };
                foreach (var entry in entries) binder.Files.Add(new BinderFile(Binder.FileFlags.Flag1,
                    entry.EntryId,
                    $"N:\\SPRJ\\data\\INTERROOT_ps4\\chr\\{character}\\tae\\{entry.EntryName}",
                    entry.Tae));
                string path = Path.Combine(characters, character + ".anibnd.dcx");
                binder.Write(path);
                return path;
            }
            string WriteBinder(string character, int entryId, byte[] tae) =>
                WriteMultiBinder(character, (entryId, character + ".tae", tae));

            object Actor(string character, string part, int entity, string sourceMap = "m99_00_00_00") => new {
                source_map = sourceMap, source_part = part, source_entity_id = entity,
                source_archetype = new { model_name = character },
            };
            object Requirement(string character, string part, int entity, int entryId, int animationCount,
                byte[] tae, IEnumerable<CharacterFfxRequirements.Witness> witnesses, string binderPath,
                IEnumerable<ulong>? decodedEventTypes = null) => new {
                format = "bb-boss-character-ffx-requirement-v1", source_map = "m99_00_00_00",
                source_part = part, source_entity_id = entity, source_character = character,
                source_anibnd_file = character + ".anibnd.dcx",
                source_anibnd_sha256 = Hash(File.ReadAllBytes(binderPath)), source_tae_entry_id = entryId,
                source_tae_entry = $"chr/{character}/tae/{character}.tae", source_tae_sha256 = Hash(tae),
                source_animation_count = animationCount, decoded_event_types = decodedEventTypes,
                typed_event_witnesses = witnesses,
                direct_effect_ids = witnesses.Select(witness => witness.EffectId).Distinct().Order(),
            };
            object TaeEntry(string character, string name, int entryId, int animationCount,
                byte[] tae, IEnumerable<CharacterFfxRequirements.Witness> witnesses,
                IEnumerable<ulong>? decodedEventTypes = null) => new {
                source_tae_entry_id = entryId, source_tae_entry = $"chr/{character}/tae/{name}",
                source_tae_sha256 = Hash(tae), source_animation_count = animationCount,
                decoded_event_types = decodedEventTypes, typed_event_witnesses = witnesses,
                direct_effect_ids = witnesses.Select(witness => witness.EffectId).Distinct().Order(),
            };
            object RequirementV2(string character, string part, int entity, string binderPath,
                object[] entries, IEnumerable<int> directEffects, string sourceMap = "m99_00_00_00") => new {
                format = "bb-boss-character-ffx-requirement-v2", source_map = sourceMap,
                source_part = part, source_entity_id = entity, source_character = character,
                source_anibnd_file = character + ".anibnd.dcx",
                source_anibnd_sha256 = Hash(File.ReadAllBytes(binderPath)),
                source_tae_entries = entries, direct_effect_ids = directEffects,
            };
            JsonObject SyntheticPlan(byte[] firstTae, List<CharacterFfxRequirements.Witness> firstWitnesses,
                byte[] secondTae, List<CharacterFfxRequirements.Witness> secondWitnesses,
                string firstBinder, string secondBinder) => (JsonObject)JsonSerializer.SerializeToNode(new {
                    boss_actor_initializations = new[] {Actor("c9000", "c9000_0000", 9900800)},
                    boss_actor_additions = new[] {Actor("c9001", "c9001_0000", 9900801)},
                    boss_character_ffx_requirements = new[] {
                        Requirement("c9000", "c9000_0000", 9900800, 3000000, 2, firstTae, firstWitnesses, firstBinder),
                        Requirement("c9001", "c9001_0000", 9900801, 3000000, 1, secondTae, secondWitnesses, secondBinder),
                    },
                }, json)!;
            void Save(JsonObject value) => File.WriteAllText(plan, value.ToJsonString());

            var first = TAE((0, [(100UL, 111), (5UL, 9), (118UL, 333),
                    (119UL, 444)]),
                (3000, [(96UL, 222)]));
            var second = TAE((0, [(5UL, 9)]));
            string firstBinder = WriteBinder("c9000", 3000000, first.Bytes);
            string secondBinder = WriteBinder("c9001", 3000000, second.Bytes);
            var valid = SyntheticPlan(first.Bytes, first.Witnesses, second.Bytes, second.Witnesses,
                firstBinder, secondBinder);
            Save(valid);
            var verified = CharacterFfxRequirements.Validate(plan, characters);
            Need(verified.Count == 2 && verified[0].SourceTaeEntries.Single().TypedEventWitnesses.Count == 3
                && verified[0].DirectEffectIds.SequenceEqual(new[] {111, 222, 333}),
                "typed 96/100/118 witnesses and direct effects verify");
            Need(verified[1].SourceTaeEntries.Single().TypedEventWitnesses.Count == 0
                && verified[1].DirectEffectIds.Count == 0,
                "a materialized source character can prove an empty typed witness set");
            Need(verified[0].SourceTaeEntries.Single().TypedEventWitnesses
                    .All(row => row.EventType is 96 or 100 or 118)
                && verified[0].SourceTaeEntries.Single().DecodedEventTypes.SequenceEqual(
                    new ulong[] {96, 100, 118})
                && verified[0].CoverageScope == "partial-typed-witness"
                && verified[0].FxrDeliveryStatus == "not-validated",
                "typed proof scope is explicitly limited and does not claim all TAE combat closure");
            Need(verified[0].SourceMap == "m99_00_00_00" && verified[0].SourcePart == "c9000_0000"
                && verified[0].SourceEntityId == 9900800,
                "verification receipts distinguish exact materialized actor bindings");

            var multiFirst = TAE((10, [(100UL, 701), (118UL, 703)]));
            var multiSecond = TAE((20, [(96UL, 702)]), (21, [(5UL, 9)]));
            string multiBinder = WriteMultiBinder("c9002",
                (5000000, "a00.tae", multiFirst.Bytes),
                (5000100, "a100.tae", multiSecond.Bytes));
            var multiPlan = (JsonObject)JsonSerializer.SerializeToNode(new {
                boss_actor_additions = new[] {Actor("c9002", "c9002_0000", 9900802)},
                boss_character_ffx_requirements = new[] {
                    RequirementV2("c9002", "c9002_0000", 9900802, multiBinder, [
                        TaeEntry("c9002", "a00.tae", 5000000, 1,
                            multiFirst.Bytes, multiFirst.Witnesses),
                        TaeEntry("c9002", "a100.tae", 5000100, 2,
                            multiSecond.Bytes, multiSecond.Witnesses),
                    ], new[] {701, 702, 703}),
                },
            }, json)!;
            Save(multiPlan);
            var multiVerified = CharacterFfxRequirements.Validate(plan, characters).Single();
            Need(multiVerified.SourceTaeEntries.Select(entry =>
                    (entry.SourceTaeEntryId, entry.SourceTaeEntry)).SequenceEqual(new[] {
                        (5000000, "chr/c9002/tae/a00.tae"),
                        (5000100, "chr/c9002/tae/a100.tae"),
                    }) && multiVerified.DirectEffectIds.SequenceEqual(new[] {701, 702, 703}),
                "v2 verifies deterministic exact identities and aggregate roots for multiple TAE entries");
            var omittedV2Profile = (JsonObject)multiPlan.DeepClone();
            foreach (var node in omittedV2Profile["boss_character_ffx_requirements"]![0]!
                ["source_tae_entries"]!.AsArray()) node!.AsObject().Remove("decoded_event_types");
            Save(omittedV2Profile);
            Need(CharacterFfxRequirements.Validate(plan, characters).Single().SourceTaeEntries
                .All(entry => entry.DecodedEventTypes.SequenceEqual(new ulong[] {96, 100, 118})),
                "v2 entries that predate decoded_event_types retain the exact legacy profile");
            string multiReceipt = JsonSerializer.Serialize(multiVerified, json);
            Need(multiReceipt.Contains("source_tae_entry_id")
                && multiReceipt.Contains("source_tae_entry")
                && multiReceipt.Contains("decoded_event_types")
                && multiReceipt.Contains("partial-typed-witness")
                && multiReceipt.Contains("not-validated"),
                "v2 receipt preserves entry identity, decoded scope, and explicit non-delivery status");

            ulong[] expandedProfile = [96, 99, 100, 108, 109, 112, 118];
            var expanded = TAEFor(expandedProfile, (30, [
                (96UL, 801), (99UL, 802), (100UL, 803), (108UL, 804),
                (109UL, 805), (112UL, 806), (118UL, 807), (116UL, 808),
            ]));
            string expandedBinder = WriteMultiBinder("c9003",
                (5000000, "a00.tae", expanded.Bytes));
            var expandedPlan = (JsonObject)JsonSerializer.SerializeToNode(new {
                boss_actor_additions = new[] {Actor("c9003", "c9003_0000", 9900804)},
                boss_character_ffx_requirements = new[] {
                    RequirementV2("c9003", "c9003_0000", 9900804, expandedBinder, [
                        TaeEntry("c9003", "a00.tae", 5000000, 1, expanded.Bytes,
                            expanded.Witnesses, expandedProfile),
                    ], Enumerable.Range(801, 7)),
                },
            }, json)!;
            Save(expandedPlan);
            var expandedVerified = CharacterFfxRequirements.Validate(plan, characters).Single();
            Need(expandedVerified.SourceTaeEntries.Single().DecodedEventTypes
                    .SequenceEqual(expandedProfile)
                && expandedVerified.SourceTaeEntries.Single().TypedEventWitnesses.Count == 7
                && expandedVerified.DirectEffectIds.SequenceEqual(Enumerable.Range(801, 7)),
                "expanded profile verifies exactly types 96/99/100/108/109/112/118 and still omits 116");

            var partialProfile = (JsonObject)expandedPlan.DeepClone();
            partialProfile["boss_character_ffx_requirements"]![0]!["source_tae_entries"]![0]!
                ["decoded_event_types"] = JsonSerializer.SerializeToNode(new ulong[] {96, 100, 112, 118});
            Save(partialProfile);
            Refused(() => CharacterFfxRequirements.Read(plan, true),
                "unsupported character FFX decoded event type profile");

            var unsortedProfile = (JsonObject)expandedPlan.DeepClone();
            unsortedProfile["boss_character_ffx_requirements"]![0]!["source_tae_entries"]![0]!
                ["decoded_event_types"] = JsonSerializer.SerializeToNode(
                    new ulong[] {99, 96, 100, 108, 109, 112, 118});
            Save(unsortedProfile);
            Refused(() => CharacterFfxRequirements.Read(plan, true),
                "unsupported character FFX decoded event type profile");

            var unknownProfile = (JsonObject)expandedPlan.DeepClone();
            unknownProfile["boss_character_ffx_requirements"]![0]!["source_tae_entries"]![0]!
                ["decoded_event_types"] = JsonSerializer.SerializeToNode(
                    new ulong[] {96, 99, 100, 108, 109, 112, 118, 119});
            Save(unknownProfile);
            Refused(() => CharacterFfxRequirements.Read(plan, true),
                "unsupported character FFX decoded event type profile");

            var floorWitness = expanded.Witnesses.Single(row => row.EventType == 112);
            byte[] floorOperandDrift = (byte[])expanded.Bytes.Clone();
            BinaryPrimitives.WriteInt32LittleEndian(
                floorOperandDrift.AsSpan(checked((int)floorWitness.ParameterOffset), 4), 899);
            expandedBinder = WriteMultiBinder("c9003",
                (5000000, "a00.tae", floorOperandDrift));
            var floorDriftPlan = (JsonObject)JsonSerializer.SerializeToNode(new {
                boss_actor_additions = new[] {Actor("c9003", "c9003_0000", 9900804)},
                boss_character_ffx_requirements = new[] {
                    RequirementV2("c9003", "c9003_0000", 9900804, expandedBinder, [
                        TaeEntry("c9003", "a00.tae", 5000000, 1, floorOperandDrift,
                            expanded.Witnesses, expandedProfile),
                    ], Enumerable.Range(801, 7)),
                },
            }, json)!;
            Save(floorDriftPlan);
            Refused(() => CharacterFfxRequirements.Validate(plan, characters),
                "typed FFX witness drift");
            expandedBinder = WriteMultiBinder("c9003",
                (5000000, "a00.tae", expanded.Bytes));

            string expandedV1Binder = WriteBinder("c9004", 3000000, expanded.Bytes);
            var expandedV1 = (JsonObject)JsonSerializer.SerializeToNode(new {
                boss_actor_additions = new[] {Actor("c9004", "c9004_0000", 9900805)},
                boss_character_ffx_requirements = new[] {
                    Requirement("c9004", "c9004_0000", 9900805, 3000000, 1,
                        expanded.Bytes, expanded.Witnesses, expandedV1Binder, expandedProfile),
                },
            }, json)!;
            Save(expandedV1);
            Need(CharacterFfxRequirements.Validate(plan, characters).Single()
                    .SourceTaeEntries.Single().DecodedEventTypes.SequenceEqual(expandedProfile),
                "v1 may explicitly opt into the expanded profile while omission remains legacy");

            var sharedMulti = (JsonObject)multiPlan.DeepClone();
            sharedMulti["boss_actor_additions"]!.AsArray().Add(JsonSerializer.SerializeToNode(
                Actor("c9002", "c9002_0001", 9900803), json));
            var sharedMultiRequirement = sharedMulti["boss_character_ffx_requirements"]![0]!.DeepClone();
            sharedMultiRequirement["source_part"] = "c9002_0001";
            sharedMultiRequirement["source_entity_id"] = 9900803;
            sharedMulti["boss_character_ffx_requirements"]!.AsArray().Add(sharedMultiRequirement);
            Save(sharedMulti);
            Need(CharacterFfxRequirements.Read(plan, true).Count == 2,
                "actors sharing a multi-TAE archive may declare the same complete proof set");
            var conflictingProfile = (JsonObject)sharedMulti.DeepClone();
            conflictingProfile["boss_character_ffx_requirements"]![1]!["source_tae_entries"]![0]!
                ["decoded_event_types"] = JsonSerializer.SerializeToNode(expandedProfile);
            Save(conflictingProfile);
            Refused(() => CharacterFfxRequirements.Read(plan, true),
                "conflicting character FFX animation binder declarations");
            sharedMulti["boss_character_ffx_requirements"]![1]!["source_tae_entries"]![1]!
                ["source_tae_sha256"] = new string('1', 64);
            Save(sharedMulti);
            Refused(() => CharacterFfxRequirements.Read(plan, true),
                "conflicting character FFX animation binder declarations");

            var outsideModelDirectory = (JsonObject)multiPlan.DeepClone();
            outsideModelDirectory["boss_character_ffx_requirements"]![0]!["source_tae_entries"]![0]!
                ["source_tae_entry"] = "chr/c9001/tae/a00.tae";
            Save(outsideModelDirectory);
            Refused(() => CharacterFfxRequirements.Read(plan, true),
                "invalid character FFX TAE entry path");

            var nonNormalizedPath = (JsonObject)multiPlan.DeepClone();
            nonNormalizedPath["boss_character_ffx_requirements"]![0]!["source_tae_entries"]![0]!
                ["source_tae_entry"] = "/chr/c9002/tae/a00.tae";
            Save(nonNormalizedPath);
            Refused(() => CharacterFfxRequirements.Read(plan, true),
                "invalid character FFX TAE entry path");

            var prefixedDeclaredPath = (JsonObject)multiPlan.DeepClone();
            prefixedDeclaredPath["boss_character_ffx_requirements"]![0]!["source_tae_entries"]![0]!
                ["source_tae_entry"] = "other/chr/c9002/tae/a00.tae";
            Save(prefixedDeclaredPath);
            Refused(() => CharacterFfxRequirements.Read(plan, true),
                "invalid character FFX TAE entry path");

            var unsortedEntries = (JsonObject)multiPlan.DeepClone();
            var unsorted = unsortedEntries["boss_character_ffx_requirements"]![0]!["source_tae_entries"]!.AsArray();
            JsonNode firstEntry = unsorted[0]!.DeepClone();
            JsonNode secondEntry = unsorted[1]!.DeepClone();
            unsorted[0] = secondEntry;
            unsorted[1] = firstEntry;
            Save(unsortedEntries);
            Refused(() => CharacterFfxRequirements.Read(plan, true),
                "character FFX TAE entries must be sorted");

            var wrongAggregate = (JsonObject)multiPlan.DeepClone();
            wrongAggregate["boss_character_ffx_requirements"]![0]!["direct_effect_ids"] =
                JsonSerializer.SerializeToNode(new[] {701, 703});
            Save(wrongAggregate);
            Refused(() => CharacterFfxRequirements.Read(plan, true),
                "aggregate direct effects do not summarize TAE entries");

            var secondEntryDrift = (JsonObject)multiPlan.DeepClone();
            secondEntryDrift["boss_character_ffx_requirements"]![0]!["source_tae_entries"]![1]!
                ["source_tae_sha256"] = new string('0', 64);
            Save(secondEntryDrift);
            Refused(() => CharacterFfxRequirements.Validate(plan, characters),
                "TAE provenance drift");

            Refused(() => CharacterFfxRequirements.Validate(plan, null),
                "require original --characters inputs");
            string empty = Path.Combine(root, "empty.json"); File.WriteAllText(empty, "{}");
            Need(CharacterFfxRequirements.Validate(empty, characters).Count == 0,
                "plans without character requirements remain unaffected");

            var changedWitness = (JsonObject)valid.DeepClone();
            changedWitness["boss_character_ffx_requirements"]![0]!["typed_event_witnesses"]![0]!["effect_id"] = 333;
            changedWitness["boss_character_ffx_requirements"]![0]!["direct_effect_ids"] =
                JsonSerializer.SerializeToNode(new[] {222, 333});
            Save(changedWitness);
            Refused(() => CharacterFfxRequirements.Validate(plan, characters), "typed FFX witness drift");

            var missingWitness = (JsonObject)valid.DeepClone();
            missingWitness["boss_character_ffx_requirements"]![0]!["typed_event_witnesses"]!.AsArray().RemoveAt(0);
            missingWitness["boss_character_ffx_requirements"]![0]!["direct_effect_ids"] =
                JsonSerializer.SerializeToNode(new[] {222, 333});
            Save(missingWitness);
            Refused(() => CharacterFfxRequirements.Validate(plan, characters), "typed FFX witness drift");

            var bladeWitness = first.Witnesses.Single(row => row.EventType == 118);
            byte[] bladeOperandDrift = (byte[])first.Bytes.Clone();
            BinaryPrimitives.WriteInt32LittleEndian(
                bladeOperandDrift.AsSpan(checked((int)bladeWitness.ParameterOffset), 4), 334);
            firstBinder = WriteBinder("c9000", 3000000, bladeOperandDrift);
            var bladeOperandPlan = SyntheticPlan(bladeOperandDrift, first.Witnesses,
                second.Bytes, second.Witnesses, firstBinder, secondBinder);
            Save(bladeOperandPlan);
            Refused(() => CharacterFfxRequirements.Validate(plan, characters),
                "typed FFX witness drift");
            firstBinder = WriteBinder("c9000", 3000000, first.Bytes);

            var missingActor = (JsonObject)valid.DeepClone();
            missingActor["boss_character_ffx_requirements"]![1]!["source_entity_id"] = 9900899;
            Save(missingActor);
            Refused(() => CharacterFfxRequirements.Validate(plan, characters), "not bound to a materialized source actor");

            var uncoveredActor = (JsonObject)valid.DeepClone();
            uncoveredActor["boss_actor_additions"]!.AsArray().Add(JsonSerializer.SerializeToNode(
                Actor("c9000", "c9000_0001", 9900802), json));
            Save(uncoveredActor);
            Refused(() => CharacterFfxRequirements.Validate(plan, characters), "lacks a character FFX requirement");

            var sharedCharacter = (JsonObject)valid.DeepClone();
            sharedCharacter["boss_actor_additions"]!.AsArray().Add(JsonSerializer.SerializeToNode(
                Actor("c9000", "c9000_0001", 9900802), json));
            var sharedRequirement = sharedCharacter["boss_character_ffx_requirements"]![0]!.DeepClone();
            sharedRequirement["source_part"] = "c9000_0001";
            sharedRequirement["source_entity_id"] = 9900802;
            sharedCharacter["boss_character_ffx_requirements"]!.AsArray().Add(sharedRequirement);
            Save(sharedCharacter);
            var sharedVerified = CharacterFfxRequirements.Validate(plan, characters);
            Need(sharedVerified.Count == 3 && sharedVerified.Count(row => row.SourceCharacter == "c9000") == 2,
                "distinct actor bindings may share one identically pinned character archive");

            var mixedVersions = (JsonObject)sharedCharacter.DeepClone();
            var mixed = mixedVersions["boss_character_ffx_requirements"]![2]!.AsObject();
            mixed["format"] = "bb-boss-character-ffx-requirement-v2";
            mixed["source_tae_entries"] = new JsonArray(new JsonObject {
                ["source_tae_entry_id"] = mixed["source_tae_entry_id"]!.DeepClone(),
                ["source_tae_entry"] = mixed["source_tae_entry"]!.DeepClone(),
                ["source_tae_sha256"] = mixed["source_tae_sha256"]!.DeepClone(),
                ["source_animation_count"] = mixed["source_animation_count"]!.DeepClone(),
                ["typed_event_witnesses"] = mixed["typed_event_witnesses"]!.DeepClone(),
                ["direct_effect_ids"] = mixed["direct_effect_ids"]!.DeepClone(),
            });
            foreach (string property in new[] {"source_tae_entry_id", "source_tae_entry",
                "source_tae_sha256", "source_animation_count", "typed_event_witnesses"})
                mixed.Remove(property);
            Save(mixedVersions);
            var mixedVerified = CharacterFfxRequirements.Validate(plan, characters);
            Need(mixedVerified.Count == 3
                && mixedVerified.Where(row => row.SourceCharacter == "c9000")
                    .All(row => row.SourceTaeEntries.Count == 1),
                "equivalent v1 and normalized one-entry v2 proofs may share an archive");

            var conflictingArchive = (JsonObject)sharedCharacter.DeepClone();
            conflictingArchive["boss_character_ffx_requirements"]![2]!["source_tae_sha256"] = new string('0', 64);
            Save(conflictingArchive);
            Refused(() => CharacterFfxRequirements.Read(plan, true),
                "conflicting character FFX animation binder declarations");

            var duplicateBinding = (JsonObject)valid.DeepClone();
            duplicateBinding["boss_character_ffx_requirements"]!.AsArray().Add(
                duplicateBinding["boss_character_ffx_requirements"]![0]!.DeepClone());
            Save(duplicateBinding);
            Refused(() => CharacterFfxRequirements.Read(plan, true),
                "duplicate character FFX actor binding");

            var badType = (JsonObject)valid.DeepClone();
            badType["boss_character_ffx_requirements"]![0]!["typed_event_witnesses"]![0]!["event_type"] = 95;
            Save(badType);
            Refused(() => CharacterFfxRequirements.Read(plan, true), "invalid character FFX typed witness");

            byte[] malformed = (byte[])first.Bytes.Clone();
            BinaryPrimitives.WriteInt64LittleEndian(malformed.AsSpan(0x68, 8), long.MaxValue);
            firstBinder = WriteBinder("c9000", 3000000, malformed);
            var malformedPlan = SyntheticPlan(malformed, first.Witnesses, second.Bytes, second.Witnesses,
                firstBinder, secondBinder);
            Save(malformedPlan);
            Refused(() => CharacterFfxRequirements.Validate(plan, characters), "outside the file");

            firstBinder = WriteBinder("c9000", 3000000, first.Bytes);
            var provenance = SyntheticPlan(first.Bytes, first.Witnesses, second.Bytes, second.Witnesses,
                firstBinder, secondBinder);
            provenance["boss_character_ffx_requirements"]![0]!["source_anibnd_sha256"] = new string('0', 64);
            Save(provenance);
            Refused(() => CharacterFfxRequirements.Validate(plan, characters), "animation binder provenance drift");

            var taeProvenance = SyntheticPlan(first.Bytes, first.Witnesses, second.Bytes, second.Witnesses,
                firstBinder, secondBinder);
            taeProvenance["boss_character_ffx_requirements"]![0]!["source_tae_sha256"] = new string('0', 64);
            Save(taeProvenance);
            Refused(() => CharacterFfxRequirements.Validate(plan, characters), "TAE provenance drift");

            Need(CharacterFfxRequirements.Validate(empty, null).Count == 0,
                "unused verifier does not require character inputs");

            string? originalCharacters = Environment.GetEnvironmentVariable("BB_ORIGINAL_CHARACTER_DIR");
            if (originalCharacters is not null) {
                object OriginalRequirement(string character, string part, int entity, string binderHash,
                    string taeHash, int animationCount, CharacterFfxRequirements.Witness[] witnesses,
                    string sourceMap = "m36_00_00_00") => new {
                    format = "bb-boss-character-ffx-requirement-v1", source_map = sourceMap,
                    source_part = part, source_entity_id = entity, source_character = character,
                    source_anibnd_file = character + ".anibnd.dcx", source_anibnd_sha256 = binderHash,
                    source_tae_entry_id = 3000000, source_tae_entry = $"chr/{character}/tae/{character}.tae",
                    source_tae_sha256 = taeHash, source_animation_count = animationCount,
                    typed_event_witnesses = witnesses,
                    direct_effect_ids = witnesses.Select(witness => witness.EffectId).Distinct().Order(),
                };
                var originalPlan = new {
                    boss_actor_initializations = new[] {
                        Actor("c4540", "c4540_0000", 3600800, "m36_00_00_00"),
                        Actor("c4510", "c4510_0000", 3400800, "m34_00_00_00"),
                    },
                    boss_actor_additions = new[] {
                        Actor("c4541", "c4541_0000", 3600801, "m36_00_00_00"),
                        Actor("c4543", "c4543_0000", 3600803, "m36_00_00_00"),
                        Actor("c4510", "c4510_0002", 3400801, "m34_00_00_00"),
                    },
                    boss_character_ffx_requirements = new[] {
                        OriginalRequirement("c4540", "c4540_0000", 3600800,
                            "fc077ffe7b08e23fcc3e373a3fec6b956a6810e4d0850e8598d8897a3edf3fdf",
                            "a085796cf0b475086b4374a24c6cbbed696aa8629e8a240b2aad45137a850d2b", 82,
                            OrphanCoreWitnesses),
                        OriginalRequirement("c4541", "c4541_0000", 3600801,
                            "358ada6931411d0765d417857cafdf2c4bcaf4df20f9b1a4b4dde63faa95246c",
                            "712478fb524532cae6bdf522fa5d44286f08cc9c4fb732f3c859fc9106930918", 98,
                            OrphanPhaseWitnesses),
                        OriginalRequirement("c4543", "c4543_0000", 3600803,
                            "9a839bdeaa31b4dc0b0832b9462a44d538daaac4625e06dd8b5f76455da25665",
                            "bc189005ef3c5a0a0e162c05e225d9cb67d47a4a78619218aedb7f091190bcb7", 20,
                            []),
                        OriginalRequirement("c4510", "c4510_0000", 3400800,
                            "2bed19c088190cf831ba9f7d1b33fc89a09f03b6224843133b5032c79ec936ef",
                            "a3d653c442752a2e97f6aaf42f5ee0c48e085eea582abfb029c198f4f8de86cd", 154,
                            LudwigWitnesses, "m34_00_00_00"),
                        OriginalRequirement("c4510", "c4510_0002", 3400801,
                            "2bed19c088190cf831ba9f7d1b33fc89a09f03b6224843133b5032c79ec936ef",
                            "a3d653c442752a2e97f6aaf42f5ee0c48e085eea582abfb029c198f4f8de86cd", 154,
                            LudwigWitnesses, "m34_00_00_00"),
                    },
                };
                File.WriteAllText(plan, JsonSerializer.Serialize(originalPlan, json));
                var original = CharacterFfxRequirements.Validate(plan, originalCharacters);
                Need(original.Take(3).Select(row => row.SourceTaeEntries.Single().TypedEventWitnesses.Count)
                    .SequenceEqual(new[] {30, 55, 0}),
                    "original Orphan archives still reproduce all 85 pinned typed witnesses");
                Need(original.Take(3).SelectMany(row => row.DirectEffectIds).Distinct().Order().SequenceEqual(
                    new[] {640800, 645400, 645401, 645404, 645405, 645410, 645411, 645420, 645430,
                        650008, 650090, 650091}),
                    "original Orphan archive smoke proves nine map roots and three global roots");
                var ludwig = original.Where(row => row.SourceCharacter == "c4510").ToList();
                Need(original.Count == 5 && ludwig.Count == 2
                    && ludwig.Select(row => row.SourcePart)
                        .SequenceEqual(new[] {"c4510_0000", "c4510_0002"})
                    && ludwig.All(row => row.SourceTaeEntries.Single().TypedEventWitnesses
                        .SequenceEqual(LudwigWitnesses)),
                    "both original Ludwig source actors share one archive with 265 ordered witnesses");
                Need(ludwig[0].DirectEffectIds.Count == 39
                    && ludwig[0].SourceTaeEntries.Single().TypedEventWitnesses
                        .Where(row => row.EventType == 118)
                        .Select(row => row.EffectId).Distinct().Order()
                        .SequenceEqual(new[] {645115, 645119}),
                    "Ludwig type 118 blade events add exactly two roots beyond types 96 and 100");

                string c0000Path = Path.Combine(originalCharacters, "c0000.anibnd.dcx");
                Need(Hash(File.ReadAllBytes(c0000Path)) ==
                    "2ef1b29323c635dca1828b823a957dc7770967d7642b458bad7365375bcd32cb",
                    "original c0000 archive provenance remains pinned");
                var c0000Binder = BND4.Read(c0000Path);
                var c0000Proofs = new List<object>();
                var c0000Effects = new SortedSet<int>();
                int c0000Witnesses = 0;
                foreach (var entry in c0000Binder.Files
                    .Where(file => Regex.IsMatch(file.Name.Replace('\\', '/'),
                        @"/chr/c0000/tae/a\d+\.tae$", RegexOptions.IgnoreCase))
                    .OrderBy(file => file.ID)) {
                    var parsed = CharacterFfxRequirements.ParseTae(entry.Bytes);
                    string entryName = entry.Name.Replace('\\', '/').Split('/').Last();
                    c0000Proofs.Add(TaeEntry("c0000", entryName, entry.ID,
                        parsed.AnimationCount, entry.Bytes, parsed.Witnesses));
                    foreach (int effect in parsed.Witnesses.Select(witness => witness.EffectId))
                        c0000Effects.Add(effect);
                    c0000Witnesses += parsed.Witnesses.Count;
                }
                var c0000Plan = (JsonObject)JsonSerializer.SerializeToNode(new {
                    boss_actor_additions = new[] {
                        Actor("c0000", "c0000_0005", 2600850, "m26_00_00_00"),
                    },
                    boss_character_ffx_requirements = new[] {
                        RequirementV2("c0000", "c0000_0005", 2600850, c0000Path,
                            c0000Proofs.ToArray(), c0000Effects, "m26_00_00_00"),
                    },
                }, json)!;
                Save(c0000Plan);
                var c0000 = CharacterFfxRequirements.Validate(plan, originalCharacters).Single();
                Need(c0000.SourceTaeEntries.Count == 80 && c0000Witnesses == 4742
                    && c0000.SourceTaeEntries.Sum(entry => entry.TypedEventWitnesses.Count) == 4742
                    && c0000.DirectEffectIds.Count == 229,
                    "original c0000 archive census verifies 80 exact TAE entries without claiming actor selection");

                string[] expandedModels = [
                    "c0000", "c1050", "c1400", "c2050", "c2090", "c2100", "c2120", "c2121",
                    "c2320", "c2321", "c2500", "c2510", "c2570", "c2571", "c2710", "c2720",
                    "c4030", "c4031", "c4500", "c4510", "c4520", "c4540", "c4541", "c4543",
                    "c5000", "c5020", "c5033", "c5070", "c5071", "c5072", "c5080", "c5100",
                    "c5120", "c5400", "c5510", "c8050", "c9010",
                ];
                var expandedActors = new List<object>();
                var expandedRequirements = new List<object>();
                var canonical = new StringBuilder();
                var expandedCounts = new Dictionary<ulong, int>();
                var floorRoots = new SortedSet<int>();
                int expandedEntryCount = 0;
                for (int modelIndex = 0; modelIndex < expandedModels.Length; modelIndex++) {
                    string model = expandedModels[modelIndex];
                    string binderPath = Path.Combine(originalCharacters, model + ".anibnd.dcx");
                    var binder = BND4.Read(binderPath);
                    string suffix = model == "c0000" ? @"a\d+\.tae" : model + @"\.tae";
                    var taeFiles = binder.Files.Where(file => Regex.IsMatch(
                            file.Name.Replace('\\', '/'),
                            $@"/chr/{model}/tae/{suffix}$", RegexOptions.IgnoreCase))
                        .OrderBy(file => file.ID).ToList();
                    Need(taeFiles.Count == (model == "c0000" ? 80 : 1),
                        "expanded original fixture has the pinned TAE-entry cardinality for " + model);
                    var proofs = new List<object>();
                    var modelEffects = new SortedSet<int>();
                    foreach (var entry in taeFiles) {
                        string entryName = entry.Name.Replace('\\', '/').Split('/').Last();
                        string entryPath = $"chr/{model}/tae/{entryName}";
                        string taeHash = Hash(entry.Bytes);
                        var parsed = CharacterFfxRequirements.ParseTae(entry.Bytes, expandedProfile);
                        proofs.Add(TaeEntry(model, entryName, entry.ID, parsed.AnimationCount,
                            entry.Bytes, parsed.Witnesses, expandedProfile));
                        expandedEntryCount++;
                        canonical.Append(model).Append('|').Append(entry.ID).Append('|')
                            .Append(entryPath).Append('|').Append(taeHash).Append('|')
                            .Append(parsed.AnimationCount).Append('|')
                            .AppendJoin(',', expandedProfile).Append('\n');
                        foreach (var witness in parsed.Witnesses) {
                            canonical.Append(witness.AnimationId).Append('|').Append(witness.EventIndex)
                                .Append('|').Append(witness.EventType).Append('|')
                                .Append(witness.ParameterOffset).Append('|').Append(witness.EffectId)
                                .Append('\n');
                            expandedCounts[witness.EventType] =
                                expandedCounts.GetValueOrDefault(witness.EventType) + 1;
                            modelEffects.Add(witness.EffectId);
                            if (witness.EventType == 112) floorRoots.Add(witness.EffectId);
                        }
                    }
                    int entity = 9910000 + modelIndex;
                    string part = model + "_audit";
                    expandedActors.Add(Actor(model, part, entity));
                    expandedRequirements.Add(RequirementV2(model, part, entity, binderPath,
                        proofs.ToArray(), modelEffects));
                }
                string expandedDigest = Hash(Encoding.UTF8.GetBytes(canonical.ToString()));
                Need(expandedDigest == "36bea59efc74d89d8d7a15ca6cb0ed92f4cb6083054767629057c0ddbfe27405",
                    "expanded original ordered witness digest drift: " + expandedDigest);
                var expandedOriginalPlan = (JsonObject)JsonSerializer.SerializeToNode(new {
                    boss_actor_additions = expandedActors,
                    boss_character_ffx_requirements = expandedRequirements,
                }, json)!;
                Save(expandedOriginalPlan);
                var expandedOriginal = CharacterFfxRequirements.Validate(plan, originalCharacters);
                Need(expandedOriginal.Count == 37 && expandedEntryCount == 116
                    && expandedOriginal.Sum(row => row.SourceTaeEntries.Count) == 116,
                    "expanded original profile verifies all 37 archives and 116 exact TAE entries");
                Need(expandedCounts.GetValueOrDefault(112UL) == 31957 && floorRoots.Count == 75,
                    "expanded original profile proves all 31,957 type-112 witnesses and 75 positive operands");
                Need(new ulong[] {96, 99, 100, 108, 109, 112, 118}
                    .Select(type => expandedCounts.GetValueOrDefault(type))
                    .SequenceEqual(new[] {11468, 3, 156, 20, 12, 31957, 1025}),
                    "expanded original profile preserves the pinned ordered count for every decoded type");
                Need(expandedOriginal.SelectMany(row => row.SourceTaeEntries)
                    .All(entry => entry.DecodedEventTypes.SequenceEqual(expandedProfile)),
                    "expanded original receipt retains the explicit partial decoded profile per entry");
            }
            Console.WriteLine($"PASS: {assertions} character TAE FFX requirement assertions"
                + (originalCharacters is null ? " (original archive smoke not requested)" : " including original archives"));
        }
        finally {
            if (Path.GetDirectoryName(root) != Path.GetTempPath().TrimEnd(Path.DirectorySeparatorChar)
                || !Path.GetFileName(root).StartsWith("bb-character-ffx-"))
                throw new Exception("unsafe character FFX test cleanup path");
            Directory.Delete(root, true);
        }
    }
}
