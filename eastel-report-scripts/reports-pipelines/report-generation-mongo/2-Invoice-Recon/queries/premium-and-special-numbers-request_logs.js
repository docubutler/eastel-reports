/*
Query 14 (request_logs): Premium and special numbers.

Output columns:
- service_type
- charge_type
- call_type
- no_of_calls
- mou

Equivalent PostgreSQL:

SELECT
    'Voice' AS service_type,
    'Premium and Special Numbers' AS charge_type,
    CASE
        WHEN t.opposite_number = '600380008000' THEN '1 MOCC - 03-8000 8000'
        WHEN t.opposite_number LIKE '601300%' AND CHAR_LENGTH(COALESCE(t.opposite_number, '')) < 12 THEN '1300 Numbers'
        WHEN t.opposite_number LIKE '601700%' AND CHAR_LENGTH(COALESCE(t.opposite_number, '')) < 12 THEN '1700 Numbers'
        WHEN t.opposite_number LIKE '601800%' AND CHAR_LENGTH(COALESCE(t.opposite_number, '')) < 12 THEN '1800 Numbers'
        WHEN t.opposite_number = '60103' THEN 'Directory Assistance -Services 103'
        WHEN t.opposite_number = '60100' THEN 'Info Services - 100'
        WHEN t.opposite_number = '6015454' THEN 'Info Services - 15454'
        WHEN t.opposite_number = '6015300' THEN 'Info Services - 15300'
        WHEN t.opposite_number = '6015353' THEN 'Info Services - 15353'
        WHEN t.opposite_number = '6015404' THEN 'Info Services - 15404'
        WHEN t.opposite_number = '6015444' THEN 'Info Services - 15444'
        WHEN t.opposite_number = '6015777' THEN 'Info Services - 15777'
        WHEN t.opposite_number = '6015555' THEN 'Info Services - 15555'
        WHEN t.opposite_number = '6015999' THEN 'Info Services - 15999'
        WHEN t.opposite_number = '6013504' THEN 'Info Services - 13504'
        WHEN t.opposite_number = '6015511' THEN 'Info Services - 15511'
        WHEN t.opposite_number = '6015800' THEN 'Info Services - 15800'
        WHEN t.opposite_number = '6015995' THEN 'Info Services - 15995'
        ELSE NULL
    END AS call_type,
    COUNT(*) AS no_of_calls,
    ROUND(SUM(COALESCE(t.act_update_used_volume, 0)::numeric) / 60, 2) AS mou
FROM iot_portal_tb_request_log t
WHERE t.req_time >= '2026-04-01'
  AND t.req_time < '2026-05-01'
  AND t.rat_type = 'VO'
  AND t.service_type_sub_cd = 'MO'
  AND t.roaming_destination_id = 87
  AND t.act_update_used_volume > 0
  AND (
        t.opposite_number = '600380008000'
        OR t.opposite_number IN (
            '60103', '60100', '6015454', '6015300', '6015353', '6015404',
            '6015444', '6015777', '6015555', '6015999', '6013504', '6015511',
            '6015800', '6015995'
        )
        OR t.opposite_number LIKE '601300%'
        OR t.opposite_number LIKE '601700%'
        OR t.opposite_number LIKE '601800%'
      )
GROUP BY
    CASE
        WHEN t.opposite_number = '600380008000' THEN '1 MOCC - 03-8000 8000'
        WHEN t.opposite_number LIKE '601300%' AND CHAR_LENGTH(COALESCE(t.opposite_number, '')) < 12 THEN '1300 Numbers'
        WHEN t.opposite_number LIKE '601700%' AND CHAR_LENGTH(COALESCE(t.opposite_number, '')) < 12 THEN '1700 Numbers'
        WHEN t.opposite_number LIKE '601800%' AND CHAR_LENGTH(COALESCE(t.opposite_number, '')) < 12 THEN '1800 Numbers'
        WHEN t.opposite_number = '60103' THEN 'Directory Assistance -Services 103'
        WHEN t.opposite_number = '60100' THEN 'Info Services - 100'
        WHEN t.opposite_number = '6015454' THEN 'Info Services - 15454'
        WHEN t.opposite_number = '6015300' THEN 'Info Services - 15300'
        WHEN t.opposite_number = '6015353' THEN 'Info Services - 15353'
        WHEN t.opposite_number = '6015404' THEN 'Info Services - 15404'
        WHEN t.opposite_number = '6015444' THEN 'Info Services - 15444'
        WHEN t.opposite_number = '6015777' THEN 'Info Services - 15777'
        WHEN t.opposite_number = '6015555' THEN 'Info Services - 15555'
        WHEN t.opposite_number = '6015999' THEN 'Info Services - 15999'
        WHEN t.opposite_number = '6013504' THEN 'Info Services - 13504'
        WHEN t.opposite_number = '6015511' THEN 'Info Services - 15511'
        WHEN t.opposite_number = '6015800' THEN 'Info Services - 15800'
        WHEN t.opposite_number = '6015995' THEN 'Info Services - 15995'
        ELSE NULL
    END
HAVING
    CASE
        WHEN t.opposite_number = '600380008000' THEN '1 MOCC - 03-8000 8000'
        WHEN t.opposite_number LIKE '601300%' AND CHAR_LENGTH(COALESCE(t.opposite_number, '')) < 12 THEN '1300 Numbers'
        WHEN t.opposite_number LIKE '601700%' AND CHAR_LENGTH(COALESCE(t.opposite_number, '')) < 12 THEN '1700 Numbers'
        WHEN t.opposite_number LIKE '601800%' AND CHAR_LENGTH(COALESCE(t.opposite_number, '')) < 12 THEN '1800 Numbers'
        WHEN t.opposite_number = '60103' THEN 'Directory Assistance -Services 103'
        WHEN t.opposite_number = '60100' THEN 'Info Services - 100'
        WHEN t.opposite_number = '6015454' THEN 'Info Services - 15454'
        WHEN t.opposite_number = '6015300' THEN 'Info Services - 15300'
        WHEN t.opposite_number = '6015353' THEN 'Info Services - 15353'
        WHEN t.opposite_number = '6015404' THEN 'Info Services - 15404'
        WHEN t.opposite_number = '6015444' THEN 'Info Services - 15444'
        WHEN t.opposite_number = '6015777' THEN 'Info Services - 15777'
        WHEN t.opposite_number = '6015555' THEN 'Info Services - 15555'
        WHEN t.opposite_number = '6015999' THEN 'Info Services - 15999'
        WHEN t.opposite_number = '6013504' THEN 'Info Services - 13504'
        WHEN t.opposite_number = '6015511' THEN 'Info Services - 15511'
        WHEN t.opposite_number = '6015800' THEN 'Info Services - 15800'
        WHEN t.opposite_number = '6015995' THEN 'Info Services - 15995'
        ELSE NULL
    END IS NOT NULL
ORDER BY call_type;
*/

db.{{request_log}}.aggregate([
  {
    $match: {
      req_time: {
        $gte: ISODate("{{start_date}}"),
        $lt: ISODate("{{end_date}}")
      },
      rat_type: "VO",
      service_type_sub_cd: "MO",
      roaming_destination_id: 87,
      act_update_used_volume: { $gt: 0 },
      $or: [
        { opposite_number: "600380008000" },
        { opposite_number: "60103" },
        { opposite_number: "60100" },
        { opposite_number: "6015454" },
        { opposite_number: "6015300" },
        { opposite_number: "6015353" },
        { opposite_number: "6015404" },
        { opposite_number: "6015444" },
        { opposite_number: "6015777" },
        { opposite_number: "6015555" },
        { opposite_number: "6015999" },
        { opposite_number: "6013504" },
        { opposite_number: "6015511" },
        { opposite_number: "6015800" },
        { opposite_number: "6015995" },
        { opposite_number: { $regex: "^601300" } },
        { opposite_number: { $regex: "^601700" } },
        { opposite_number: { $regex: "^601800" } }
      ]
    }
  },
  {
    $addFields: {
      call_type: {
        $switch: {
          branches: [
            { case: { $eq: ["$opposite_number", "600380008000"] }, then: "1 MOCC - 03-8000 8000" },
            {
              case: {
                $and: [
                  { $regexMatch: { input: { $ifNull: ["$opposite_number", ""] }, regex: "^601300" } },
                  { $lt: [{ $strLenCP: { $ifNull: ["$opposite_number", ""] } }, 12] }
                ]
              },
              then: "1300 Numbers"
            },
            {
              case: {
                $and: [
                  { $regexMatch: { input: { $ifNull: ["$opposite_number", ""] }, regex: "^601700" } },
                  { $lt: [{ $strLenCP: { $ifNull: ["$opposite_number", ""] } }, 12] }
                ]
              },
              then: "1700 Numbers"
            },
            {
              case: {
                $and: [
                  { $regexMatch: { input: { $ifNull: ["$opposite_number", ""] }, regex: "^601800" } },
                  { $lt: [{ $strLenCP: { $ifNull: ["$opposite_number", ""] } }, 12] }
                ]
              },
              then: "1800 Numbers"
            },
            { case: { $eq: ["$opposite_number", "60103"] }, then: "Directory Assistance -Services 103" },
            { case: { $eq: ["$opposite_number", "60100"] }, then: "Info Services - 100" },
            { case: { $eq: ["$opposite_number", "6015454"] }, then: "Info Services - 15454" },
            { case: { $eq: ["$opposite_number", "6015300"] }, then: "Info Services - 15300" },
            { case: { $eq: ["$opposite_number", "6015353"] }, then: "Info Services - 15353" },
            { case: { $eq: ["$opposite_number", "6015404"] }, then: "Info Services - 15404" },
            { case: { $eq: ["$opposite_number", "6015444"] }, then: "Info Services - 15444" },
            { case: { $eq: ["$opposite_number", "6015777"] }, then: "Info Services - 15777" },
            { case: { $eq: ["$opposite_number", "6015555"] }, then: "Info Services - 15555" },
            { case: { $eq: ["$opposite_number", "6015999"] }, then: "Info Services - 15999" },
            { case: { $eq: ["$opposite_number", "6013504"] }, then: "Info Services - 13504" },
            { case: { $eq: ["$opposite_number", "6015511"] }, then: "Info Services - 15511" },
            { case: { $eq: ["$opposite_number", "6015800"] }, then: "Info Services - 15800" },
            { case: { $eq: ["$opposite_number", "6015995"] }, then: "Info Services - 15995" }
          ],
          default: null
        }
      }
    }
  },
  {
    $match: {
      call_type: { $ne: null }
    }
  },
  {
    $group: {
      _id: "$call_type",
      no_of_calls: { $sum: 1 },
      mou: {
        $sum: {
          $divide: [
            { $toDouble: { $ifNull: ["$act_update_used_volume", 0] } },
            60
          ]
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      service_type: { $literal: "Voice" },
      charge_type: { $literal: "Premium and Special Numbers" },
      call_type: "$_id",
      no_of_calls: 1,
      mou: 1,
      sort_order: {
        $switch: {
          branches: [
            { case: { $eq: ["$_id", "1 MOCC - 03-8000 8000"] }, then: 1 },
            { case: { $eq: ["$_id", "1300 Numbers"] }, then: 2 },
            { case: { $eq: ["$_id", "1700 Numbers"] }, then: 3 },
            { case: { $eq: ["$_id", "1800 Numbers"] }, then: 4 },
            { case: { $eq: ["$_id", "Directory Assistance -Services 103"] }, then: 5 },
            { case: { $eq: ["$_id", "Info Services - 100"] }, then: 7 },
            { case: { $eq: ["$_id", "Info Services - 15454"] }, then: 8 },
            { case: { $eq: ["$_id", "Info Services - 15300"] }, then: 9 },
            { case: { $eq: ["$_id", "Info Services - 15353"] }, then: 10 },
            { case: { $eq: ["$_id", "Info Services - 15404"] }, then: 11 },
            { case: { $eq: ["$_id", "Info Services - 15444"] }, then: 12 },
            { case: { $eq: ["$_id", "Info Services - 15777"] }, then: 13 },
            { case: { $eq: ["$_id", "Info Services - 15555"] }, then: 14 },
            { case: { $eq: ["$_id", "Info Services - 15999"] }, then: 15 },
            { case: { $eq: ["$_id", "Info Services - 13504"] }, then: 16 },
            { case: { $eq: ["$_id", "Info Services - 15511"] }, then: 17 },
            { case: { $eq: ["$_id", "Info Services - 15800"] }, then: 18 },
            { case: { $eq: ["$_id", "Info Services - 15995"] }, then: 19 }
          ],
          default: 999
        }
      }
    }
  },
  {
    $addFields: {
      mou: { $round: ["$mou", 2] }
    }
  },
  {
    $sort: {
      sort_order: 1
    }
  },
  {
    $project: {
      _id: 0,
      service_type: 1,
      charge_type: 1,
      call_type: 1,
      no_of_calls: 1,
      mou: 1
    }
  }
]);
