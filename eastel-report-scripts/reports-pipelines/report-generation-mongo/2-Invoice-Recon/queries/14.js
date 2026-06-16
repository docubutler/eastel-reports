/*
Query 14: Premium and special numbers.

Output columns:
- service_type
- charge_type
- call_type
- no_of_calls
- mou
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
        { opposite_number: { $regex: "^601300" } },
        { opposite_number: { $regex: "^601700" } },
        { opposite_number: { $regex: "^601800" } },
        { opposite_number: { $in: ["999", "112", "991", "994", "995"] } }
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
            { case: { $in: ["$opposite_number", ["999", "112", "991", "994", "995"]] }, then: "Emergency Numbers" },
            { case: { $eq: ["$opposite_number", "60100"] }, then: "Info Services - 100" },
            { case: { $eq: ["$opposite_number", "6015454"] }, then: "Info Services - 15454" },
            { case: { $eq: ["$opposite_number", "6015300"] }, then: "Info Services - 15300" },
            { case: { $eq: ["$opposite_number", "6015353"] }, then: "Info Services - 15353" },
            { case: { $eq: ["$opposite_number", "6015404"] }, then: "Info Services - 15404" },
            { case: { $eq: ["$opposite_number", "6015444"] }, then: "Info Services - 15444" },
            { case: { $eq: ["$opposite_number", "6015777"] }, then: "Info Services - 15777" }
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
          $round: [
            {
              $divide: [
                { $toDouble: { $ifNull: ["$act_update_used_volume", 0] } },
                60
              ]
            },
            2
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
            { case: { $eq: ["$_id", "Emergency Numbers"] }, then: 6 },
            { case: { $eq: ["$_id", "Info Services - 100"] }, then: 7 },
            { case: { $eq: ["$_id", "Info Services - 15454"] }, then: 8 },
            { case: { $eq: ["$_id", "Info Services - 15300"] }, then: 9 },
            { case: { $eq: ["$_id", "Info Services - 15353"] }, then: 10 },
            { case: { $eq: ["$_id", "Info Services - 15404"] }, then: 11 },
            { case: { $eq: ["$_id", "Info Services - 15444"] }, then: 12 },
            { case: { $eq: ["$_id", "Info Services - 15777"] }, then: 13 }
          ],
          default: 999
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      service_type: 1,
      charge_type: 1,
      call_type: 1,
      no_of_calls: 1,
      mou: 1,
      sort_order: 1
    }
  },
  {
    $sort: {
      sort_order: 1
    }
  },
  {
    $project: {
      sort_order: 0
    }
  }
]);
